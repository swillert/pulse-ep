"""Export a map to the OpenEP ``userdata`` structure.

`OpenEP <https://openep.io>`_ is a MATLAB platform for electroanatomic mapping
research. Its data structure — ``userdata``, with ``surface``, ``electric`` and
``rf`` — is what its analysis functions take, and it parses CARTO and Precision
itself. Writing that structure from here is worth doing for one reason above
the others: **pulse-ep reads EnSite X, and OpenEP does not.** A map from either
vendor can then go through any OpenEP analysis.

The format knowledge here comes from reading ``importcarto_mem.m`` in
`openep-core <https://github.com/openep/openep-core>`_, which is Apache-2.0.
No code is taken from it, and none from ``openep-py``, which is GPL-3.0 and
therefore not compatible with this package's licence.

What this module does *not* do is decide anything: it maps declared quantities
onto positional slots and records, in ``userdata.notes``, everything it could
not map. See :func:`to_userdata` for the one place where that gets dangerous.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    CONTACT_FORCE,
    IMPEDANCE,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
)

if TYPE_CHECKING:  # pragma: no cover
    from pulse_ep.core.epmap import EPMap

#: ``userdata.surface.act_bip`` is an ``nVertices x 2`` array whose columns are
#: activation time and bipolar voltage, and ``uni_imp_frc`` an ``nVertices x 3``
#: of unipolar voltage, impedance and contact force. The slots are positional:
#: OpenEP reads column 1 of ``act_bip`` *as* an activation time because that is
#: where an activation time goes.
SURFACE_SLOTS: dict[str, tuple[str, ...]] = {
    "act_bip": (ACTIVATION_TIME, VOLTAGE_BIPOLAR),
    "uni_imp_frc": (VOLTAGE_UNIPOLAR, IMPEDANCE, CONTACT_FORCE),
}


def _column(epmap: EPMap, kind: str, n: int) -> tuple[np.ndarray, str | None]:
    """The map's values for ``kind``, or a column of NaN and why it is empty.

    A field is registered under the name of the quantity it holds, so asking
    for a kind and asking for a name are the same question — which is what
    makes one mapping serve both vendors.
    """
    for name, field in epmap.scalar_fields.items():
        if field.kind != kind:
            continue
        values = np.asarray(field.values, dtype=float).ravel()
        if values.size != n:
            return np.full(n, np.nan), f"{name}: {values.size} values for {n} vertices"
        return values, None
    return np.full(n, np.nan), None


def surface_arrays(epmap: EPMap) -> tuple[dict[str, np.ndarray], list[str]]:
    """``act_bip`` and ``uni_imp_frc`` for a map, plus notes on what is missing.

    **A pace map's score is not written into the activation-time slot.** CARTO
    stores both in one place and pulse-ep learned to tell them apart — the
    whole point of the declared ``kind``. Writing a ``pacemap_score`` into
    ``act_bip(:,1)`` would tell OpenEP the map is an activation map, and every
    conduction-velocity or isochrone function downstream would agree. The slot
    stays NaN instead and the note says so, because a gap can be seen and a
    plausible wrong number cannot.
    """
    n = 0 if epmap.vertices is None else len(epmap.vertices)
    arrays: dict[str, np.ndarray] = {}
    notes: list[str] = []
    for slot, kinds in SURFACE_SLOTS.items():
        columns = []
        for kind in kinds:
            values, problem = _column(epmap, kind, n)
            if problem:
                notes.append(f"{slot}: {problem}")
            elif not np.isfinite(values).any():
                notes.append(f"{slot}: no {kind} on this map")
            columns.append(values)
        arrays[slot] = np.column_stack(columns) if columns else np.empty((n, 0))

    unmapped = sorted(
        {f.kind for f in epmap.scalar_fields.values()}
        - {k for kinds in SURFACE_SLOTS.values() for k in kinds}
    )
    if unmapped:
        # Said plainly rather than dropped silently: OpenEP's surface has four
        # slots and a pulse-ep map may carry a dozen quantities.
        notes.append("not representable in userdata.surface: " + ", ".join(unmapped))
    return arrays, notes


#: ``userdata.electric.annotations`` keys -> the components a measurement point
#: records them under. The names line up because both describe the same thing:
#: where a beat sits in the window recorded for it.
ANNOTATION_KEYS: dict[str, tuple[str, ...]] = {
    "referenceAnnot": ("reference",),
    "mapAnnot": ("map",),
}


def electric_arrays(epmap: EPMap) -> tuple[dict, list[str]]:
    """``userdata.electric`` for a map's measurement points.

    Positions, the operator's tags, the vendor point ids, bipolar and unipolar
    voltages, and the annotation components — which map across without
    interpretation, because pulse-ep records exactly the four OpenEP names:
    the window of interest, the reference annotation and the map annotation.

    ``egmSurfX`` and ``barDirection`` are the point projected onto the surface
    and the normal there; both are computed rather than stored, so they are
    filled only when the map has a mesh to project onto.

    Electrograms are not included. They live outside the database as Parquet
    and can dwarf everything else — the same reason importing them is opt-in —
    so a caller that wants ``egm`` supplies it separately.
    """
    points = list(epmap.measurement_points or [])
    n = len(points)
    notes: list[str] = []

    egm_x = (
        np.array([np.asarray(p.position, dtype=float) for p in points]) if n else np.empty((0, 3))
    )
    electric: dict = {
        "names": [str(p.source_id or i) for i, p in enumerate(points, start=1)],
        "tags": [list(p.tags or []) for p in points],
        "egmX": egm_x,
        "voltages": {
            "bipolar": np.array([_measure(p, VOLTAGE_BIPOLAR) for p in points]),
            "unipolar": np.array([_measure(p, VOLTAGE_UNIPOLAR) for p in points]),
        },
        "annotations": {
            key: np.array([_annotation(p, names) for p in points])
            for key, names in ANNOTATION_KEYS.items()
        },
        "electrodeNames_bip": [sorted(p.electrodes or {}) for p in points],
    }
    # OpenEP's woi is a from/to pair per point, which is how it is recorded.
    electric["annotations"]["woi"] = np.array(
        [[_annotation(p, ("woi_from",)), _annotation(p, ("woi_to",))] for p in points]
    ).reshape(n, 2)

    if epmap.vertices is not None and n:
        from scipy.spatial import cKDTree

        vertices = np.asarray(epmap.vertices, dtype=float)
        _, nearest = cKDTree(vertices).query(egm_x)
        electric["egmSurfX"] = vertices[nearest]
        if epmap.normals is not None:
            electric["barDirection"] = np.asarray(epmap.normals, dtype=float)[nearest]
        else:
            notes.append("barDirection: the map carries no vertex normals")
    elif n:
        notes.append("egmSurfX / barDirection: the map has no mesh to project onto")

    return electric, notes


def _measure(point, kind: str) -> float:
    """One point's value for a quantity, by kind rather than by name."""
    for measurement in (point.measurements or {}).values():
        if measurement.kind == kind:
            return float(measurement.value)
    return float("nan")


def _annotation(point, names: tuple[str, ...]) -> float:
    for name in names:
        value = (point.annotations or {}).get(name)
        if value is not None:
            return float(value)
    return float("nan")


#: Which contact-force channel fills which OpenEP field. The names on the left
#: are EnSite X's; a CARTO force file calls the same three ForceValue,
#: AxialAngle and LateralAngle, so the mapping is by quantity, not by spelling.
FORCE_CHANNELS: dict[str, tuple[str, ...]] = {
    "force": ("totalForce", "ForceValue"),
    "axialAngle": ("alphaAngle", "AxialAngle"),
    "lateralAngle": ("thetaAngle", "LateralAngle"),
}


def _force_channel(waveform, field: str) -> int | None:
    """Index of the channel that fills ``field``, ignoring a sensor suffix."""
    wanted = {n.casefold() for n in FORCE_CHANNELS[field]}
    for i, channel in enumerate(waveform.channels):
        base = channel.rsplit("_", 1)[0] if channel.rsplit("_", 1)[-1].isdigit() else channel
        if base.casefold() in wanted:
            return i
    return None


def force_for_points(points, windows) -> tuple[dict, list[str]]:
    """``userdata.electric.force`` from per-segment force windows.

    OpenEP wants force **per point**: a value at the annotation and the course
    around it. CARTO writes exactly that, one file per acquired point. EnSite X
    writes per *segment*, so a point's force has to be found — which is what
    the absolute times are for, ``annotations["start_time"]`` on the point and
    ``meta["start_time"]`` on the window.

    A point no window covers gets NaN and is counted in the notes. That is not
    a failure mode to hide: an export can hold a force recording from a moment
    when no mapping point was taken, and one does — its window sits 92 s after
    the last point of the study it came with.

    For EnSite X the per-point course is a *slice* of a segment window, not
    something the system recorded per point. The note says so, because the
    difference matters to anyone integrating force over time.
    """
    n = len(points)
    empty = {
        "force": np.full(n, np.nan),
        "axialAngle": np.full(n, np.nan),
        "lateralAngle": np.full(n, np.nan),
        "time_force": [np.empty((0, 2)) for _ in points],
        "time_axial": [np.empty((0, 2)) for _ in points],
        "time_lateral": [np.empty((0, 2)) for _ in points],
    }
    usable = [
        w
        for w in (windows or [])
        if str(w.signal_type).startswith("contact_force") and w.meta.get("start_time")
    ]
    if not usable:
        return empty, [] if not points else ["electric.force: no contact-force windows supplied"]

    matched = 0
    derived = False
    for i, point in enumerate(points):
        at = (point.annotations or {}).get("start_time")
        if at is None:
            continue
        for window in usable:
            begin = float(window.meta["start_time"])
            axis = np.asarray(window.time if window.time is not None else [], dtype=float)
            end = begin + (float(axis[-1]) if axis.size else 0.0)
            if not (begin <= at <= end):
                continue
            matched += 1
            derived = True
            sample = int(np.argmin(np.abs(begin + axis - at))) if axis.size else 0
            for field, target in (
                ("force", "time_force"),
                ("axialAngle", "time_axial"),
                ("lateralAngle", "time_lateral"),
            ):
                column = _force_channel(window, field)
                if column is None:
                    continue
                values = window.data[:, column]
                empty[field][i] = float(values[sample])
                empty[target][i] = np.column_stack([begin + axis, values])
            break

    notes = []
    if matched < len(points):
        notes.append(
            f"electric.force: {len(points) - matched} of {len(points)} points are not "
            "covered by any contact-force window"
        )
    if derived:
        notes.append(
            "electric.force: the per-point course is a slice of a per-segment window, "
            "not a per-point recording"
        )
    return empty, notes


def to_userdata(
    epmap: EPMap, study_name: str | None = None, force_windows: list | None = None
) -> dict:
    """The full OpenEP ``userdata`` for one map.

    ``surface.triRep`` is handed over as its two arrays, ``X`` and
    ``Triangulation``, because ``scipy.io.savemat`` writes structs and arrays
    and cannot construct a MATLAB ``triangulation`` object. The one-line
    MATLAB loader that ships beside this builds it — see
    ``examples/matlab/pe_to_openep.m``.

    Triangle indices are **1-based** here. pulse-ep counts vertices from zero,
    MATLAB from one, and this is the boundary between them.

    ``userdata.notes`` carries what could not be mapped: an empty slot, a
    quantity OpenEP's surface has no room for, a pace-mapping score that
    deliberately did not go into the activation-time column. A reader who
    trusts the structure without reading the notes should still not be misled —
    which is why the unmappable is left as NaN rather than filled.
    """
    vertices = np.empty((0, 3)) if epmap.vertices is None else np.asarray(epmap.vertices, float)
    triangles = (
        np.empty((0, 3), dtype=np.int64)
        if epmap.triangles is None
        else np.asarray(epmap.triangles, dtype=np.int64) + 1  # 0-based -> MATLAB
    )
    surface, surface_notes = surface_arrays(epmap)
    electric, electric_notes = electric_arrays(epmap)
    force, force_notes = force_for_points(list(epmap.measurement_points or []), force_windows)
    electric["force"] = force
    electric_notes.extend(force_notes)

    rim = epmap.is_vertex_at_edge
    return {
        "surface": {
            "triRep": {"X": vertices, "Triangulation": triangles},
            "isVertexAtRim": (
                np.zeros(len(vertices), dtype=bool) if rim is None else np.asarray(rim, dtype=bool)
            ),
            **surface,
        },
        "electric": electric,
        # No ablation data: pulse-ep imports VisiTag sites as placed points on
        # the *study*, not on a map, and EnSite X lesions likewise. Filling
        # userdata.rf means deciding which of a study's sites belong to which
        # map, which the exports do not say.
        "rf": {},
        "notes": [
            f"written by pulse-ep from map {epmap.map_name!r}"
            + (f" of study {study_name!r}" if study_name else ""),
            *surface_notes,
            *electric_notes,
        ],
    }


def write_userdata(
    epmap: EPMap, path, study_name: str | None = None, force_windows: list | None = None
) -> list[str]:
    """Write ``userdata`` to a MATLAB ``.mat`` file; return its notes.

    The notes are returned as well as written, so a caller sees what the
    structure could not carry without opening MATLAB.
    """
    from scipy.io import savemat

    userdata = to_userdata(epmap, study_name=study_name, force_windows=force_windows)
    savemat(str(path), {"userdata": userdata}, long_field_names=True)
    return userdata["notes"]
