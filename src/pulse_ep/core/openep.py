"""Export a map to the OpenEP ``userdata`` structure.

`OpenEP <https://openep.io>`_ is a MATLAB platform for electroanatomic mapping
research. Its data structure — ``userdata``, with ``surface``, ``electric`` and
``rf`` — is what its analysis functions take, and it parses CARTO and Precision
itself. This bridge provides database-backed access to imported maps from
either vendor for OpenEP analyses supported by the exported quantities.

The format knowledge here comes from reading ``importcarto_mem.m`` in
`openep-core <https://github.com/openep/openep-core>`_, which is Apache-2.0.
No code is taken from it, and none from ``openep-py``, which is GPL-3.0 and
therefore not compatible with this package's licence.

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    CONTACT_FORCE,
    IMPEDANCE,
    PACEMAP_SCORE,
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


def _unit_factor(kind: str, unit: str) -> float:
    """Convert only declared, compatible units to OpenEP's positional units."""
    units = {
        ACTIVATION_TIME: {"ms": 1, "s": 1000, "us": 0.001, "µs": 0.001},
        VOLTAGE_BIPOLAR: {"mV": 1, "V": 1000, "uV": 0.001, "µV": 0.001},
        VOLTAGE_UNIPOLAR: {"mV": 1, "V": 1000, "uV": 0.001, "µV": 0.001},
        CONTACT_FORCE: {"g": 1},
        IMPEDANCE: {"ohm": 1, "Ohm": 1, "Ω": 1, "kohm": 1000, "kΩ": 1000},
        PACEMAP_SCORE: {"%": 1},
    }
    return units.get(kind, {}).get(unit, float("nan"))


def _column(epmap: EPMap, kind: str, n: int) -> tuple[np.ndarray, str | None]:
    """The map's values for ``kind``, or a column of NaN and why it is empty.

    Select by declared quantity; named containers retain the original units.
    """
    for name, field in epmap.scalar_fields.items():
        if field.kind != kind:
            continue
        values = np.asarray(field.values, dtype=float).ravel()
        if values.size != n:
            return np.full(n, np.nan), f"{name}: {values.size} values for {n} vertices"
        factor = _unit_factor(kind, field.unit)
        if not np.isfinite(factor):
            return np.full(
                n, np.nan
            ), f"{name}: unsupported unit {field.unit!r}; original retained in signalMaps"
        values = values * factor
        if field.status_mask is not None:
            mask = np.asarray(field.status_mask, bool).ravel()
            if mask.size != n:
                return np.full(
                    n, np.nan
                ), f"{name}: invalid-length status mask; standard column omitted"
            values[~mask] = np.nan
        return values, None
    return np.full(n, np.nan), None


def _surface_activation_kind(epmap: EPMap) -> str:
    """Use real LAT where present; otherwise encode a pace map in that slot."""
    kinds = {f.kind for f in epmap.scalar_fields.values()}
    if ACTIVATION_TIME not in kinds and PACEMAP_SCORE in kinds:
        return PACEMAP_SCORE
    return ACTIVATION_TIME


def _point_activation_kind(point, surface_kind: str) -> str:
    kinds = {m.kind for m in (point.measurements or {}).values()}
    if ACTIVATION_TIME in kinds:
        return ACTIVATION_TIME
    if PACEMAP_SCORE in kinds or surface_kind == PACEMAP_SCORE:
        return PACEMAP_SCORE
    return ACTIVATION_TIME


def surface_arrays(epmap: EPMap) -> tuple[dict[str, np.ndarray], list[str]]:
    """Surface slots, retaining CARTO's negative-score pace-mapping convention.

    A pace score of 90% becomes -90 in ``act_bip(:,1)``. A declared LAT field
    takes precedence on mixed maps; it keeps its sign and is converted to ms. The notes
    and ``userdata.pulse_ep`` distinguish score encoding from activation time.
    """
    n = 0 if epmap.vertices is None else len(epmap.vertices)
    arrays: dict[str, np.ndarray] = {}
    notes: list[str] = []
    activation_kind = _surface_activation_kind(epmap)
    mapped_kinds = set()
    for slot, kinds in SURFACE_SLOTS.items():
        columns = []
        for kind in kinds:
            source_kind = activation_kind if kind == ACTIVATION_TIME else kind
            mapped_kinds.add(source_kind)
            values, problem = _column(epmap, source_kind, n)
            if source_kind == PACEMAP_SCORE:
                values = -np.abs(values)
                notes.append(
                    "act_bip(:,1): pacemap_score encoded as negative score (%), "
                    "not activation time (ms)"
                )
            if problem:
                notes.append(f"{slot}: {problem}")
            elif not np.isfinite(values).any():
                notes.append(f"{slot}: no {source_kind} on this map")
            columns.append(values)
        arrays[slot] = np.column_stack(columns) if columns else np.empty((n, 0))

    unmapped = sorted({f.kind for f in epmap.scalar_fields.values()} - mapped_kinds)
    if unmapped:
        notes.append("additional quantities in surface.signalMaps: " + ", ".join(unmapped))
    return arrays, notes


def signal_maps(epmap: EPMap) -> tuple[list[dict], list[str]]:
    """All named vertex fields in OpenEP's extensible signal-map container.

    This also retains original values for quantities encoded differently in
    the positional slots, such as positive pace scores and duplicate kinds.
    Extra metadata carry the declared unit, provenance and validity mask.
    ``propSettings`` stays empty because acquisition settings are not stored
    on a ScalarField.
    """
    n = 0 if epmap.vertices is None else len(epmap.vertices)
    records, notes = [], []
    for name, field in epmap.scalar_fields.items():
        values = np.asarray(field.values, dtype=float).ravel()
        if values.size != n:
            notes.append(f"signalMaps: {name} omitted ({values.size} values for {n} vertices)")
            continue
        mask = np.empty(0, dtype=bool)
        if field.status_mask is not None:
            mask = np.asarray(field.status_mask, dtype=bool).ravel()
            if mask.size != n:
                notes.append(f"signalMaps: {name} has an invalid-length status mask; mask omitted")
                mask = np.empty(0, dtype=bool)
        records.append(
            {
                "name": name,
                "map": values,
                "propSettings": "",
                "kind": field.kind,
                "unit": field.unit,
                "source": field.source or "",
                "statusMask": mask,
            }
        )
    return records, notes


def signal_properties(points) -> list[dict]:
    """All named point measurements, with NaN at points lacking a value.

    A shared name does not justify mixing different kinds or units. Those
    combinations remain separate properties; fieldName identifies the source
    key while OpenEP's name and value arrays both follow the point order.
    """
    identities = sorted(
        {
            (name, m.kind, m.unit)
            for point in points
            for name, m in (point.measurements or {}).items()
        }
    )
    records = []
    for name, kind, unit in identities:
        values = np.full(len(points), np.nan)
        names = []
        for i, point in enumerate(points):
            measurement = (point.measurements or {}).get(name)
            matches = measurement is not None and (measurement.kind, measurement.unit) == (
                kind,
                unit,
            )
            names.append(name if matches else "")
            if matches:
                values[i] = float(measurement.value)
        records.append(
            {
                "name": names,
                "fieldName": name,
                "value": values,
                "propSettings": "",
                "kind": kind,
                "unit": unit,
            }
        )
    return records


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
    voltages, and available annotation components. Pace-mapping annotations
    encode the negative score in ``mapAnnot - referenceAnnot``, matching the
    surface convention. Missing scores remain NaN.

    ``egmSurfX`` and ``barDirection`` are the point projected onto the surface
    and the normal there; both are computed rather than stored, so they are
    filled only when the map has a mesh to project onto.

    Waveforms are added by :func:`to_userdata` when explicitly requested.
    """
    points = list(epmap.measurement_points or [])
    n = len(points)
    notes: list[str] = []
    unsupported = sorted(
        {
            (m.kind, m.unit)
            for p in points
            for m in (p.measurements or {}).values()
            if m.kind in {ACTIVATION_TIME, PACEMAP_SCORE, VOLTAGE_BIPOLAR, VOLTAGE_UNIPOLAR}
            and not np.isfinite(_unit_factor(m.kind, m.unit))
        }
    )
    for kind, unit in unsupported:
        notes.append(
            f"electric: {kind} with unsupported unit {unit!r} omitted from standard values; original retained in signalProps"
        )

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
        "signalProps": signal_properties(points),
    }
    # OpenEP's woi is a from/to pair per point, which is how it is recorded.
    electric["annotations"]["woi"] = np.array(
        [[_annotation(p, ("woi_from",)), _annotation(p, ("woi_to",))] for p in points]
    ).reshape(n, 2)

    # Reconstruct the annotation difference from the declared score, not
    # from overloaded raw annotations (which may contain an unscored beat).
    # Preserve the reference offset when present. A score with no reference
    # uses zero as an encoding origin, not as an acquired timing landmark.
    surface_kind = _surface_activation_kind(epmap)
    encoded = 0
    zero_references = 0
    for i, point in enumerate(points):
        if _point_activation_kind(point, surface_kind) != PACEMAP_SCORE:
            continue
        score = _measure(point, PACEMAP_SCORE)
        ref = electric["annotations"]["referenceAnnot"][i]
        if np.isfinite(score) and not np.isfinite(ref):
            ref = 0.0
            electric["annotations"]["referenceAnnot"][i] = ref
            zero_references += 1
        electric["annotations"]["mapAnnot"][i] = ref - abs(score)
        encoded += 1
    if encoded:
        notes.append(
            f"electric.annotations: {encoded} pace-mapping points use "
            "mapAnnot - referenceAnnot = negative score (%); missing scores stay NaN"
        )
    if zero_references:
        notes.append(
            f"electric.annotations: {zero_references} pace-mapping points use a zero "
            "reference solely to encode the score; no acquired reference was available"
        )

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
            return float(measurement.value) * _unit_factor(kind, measurement.unit)
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
    matches = []
    for i, channel in enumerate(waveform.channels):
        base = channel.rsplit("_", 1)[0] if channel.rsplit("_", 1)[-1].isdigit() else channel
        if base.casefold() in wanted:
            matches.append(i)
    return matches[0] if len(matches) == 1 else None


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

    For EnSite X the course is the matched segment recording, expressed
    relative to each point's reference time. It was not recorded per point.
    """
    n = len(points)
    result = {field: np.full(n, np.nan) for field in FORCE_CHANNELS}
    courses = {
        field: [np.empty((0, 2)) for _ in points]
        for field in ("time_force", "time_axial", "time_lateral")
    }
    usable = [w for w in (windows or []) if str(w.signal_type).startswith("contact_force")]
    matched, derived = 0, False
    for i, point in enumerate(points):
        candidates = []
        at = (point.annotations or {}).get("start_time")
        for window in usable:
            if window.meta.get("format") == "carto_force":
                if str(window.meta.get("point_id")) == str(point.source_id):
                    candidates.append(window)
            else:
                begin = window.meta.get("start_time")
                axis = np.asarray(window.time if window.time is not None else [], float)
                if (
                    at is not None
                    and begin is not None
                    and len(axis)
                    and begin + axis[0] <= at <= begin + axis[-1]
                ):
                    candidates.append(window)
        if len(candidates) != 1:
            continue
        window = candidates[0]
        axis = np.asarray(window.time if window.time is not None else [], float)
        if not len(axis):
            continue
        direct = window.meta.get("format") == "carto_force"
        if direct:
            relative_ms = axis
            sample = int(np.argmin(np.abs(axis)))
        else:
            derived = True
            relative_ms = (float(window.meta["start_time"]) + axis - at) * 1000
            sample = int(np.argmin(np.abs(relative_ms)))
        matched += 1
        for field, target in (
            ("force", "time_force"),
            ("axialAngle", "time_axial"),
            ("lateralAngle", "time_lateral"),
        ):
            column = _force_channel(window, field)
            if column is None:
                continue
            values = np.asarray(window.data[:, column], float)
            instant = window.meta.get("instantaneous", {}).get(window.channels[column])
            result[field][i] = float(instant) if instant is not None else values[sample]
            courses[target][i] = np.column_stack([relative_ms, values])
    for field, rows in courses.items():
        width = max((len(row) for row in rows), default=0)
        array = np.full((n, width, 2), np.nan)
        for i, row in enumerate(rows):
            array[i, : len(row)] = row
        result[field] = array
    notes = []
    if not usable and n:
        notes.append("electric.force: no contact-force windows supplied")
    elif matched < n:
        notes.append(
            f"electric.force: {n - matched} of {n} points are not covered by a unique contact-force window"
        )
    if derived:
        notes.append(
            "electric.force: each course retains the matched per-segment recording; it was not recorded per point"
        )
    if matched:
        notes.append(
            "electric.force: time courses use milliseconds relative to the point's reference/acquisition origin"
        )
    return result, notes


def to_userdata(
    epmap: EPMap,
    study_name: str | None = None,
    force_windows: list | None = None,
    system_name: str | None = None,
    *,
    signal_windows: list | None = None,
    ablation_points: list | None = None,
    ecg_channels: list[str] | None = None,
    signal_scale_to_mv: float | None = None,
) -> dict:
    """The full OpenEP ``userdata`` for one map.

    ``surface.triRep`` is handed over as its two arrays, ``X`` and
    ``Triangulation``, because ``scipy.io.savemat`` writes structs and arrays
    and cannot construct a MATLAB ``triangulation`` object. The one-line
    MATLAB loader that ships beside this builds it — see
    ``examples/matlab/pe_to_openep.m``.

    Triangle indices are **1-based** here. pulse-ep counts vertices from zero,
    MATLAB from one, and this is the boundary between them.

    ``userdata.notes`` records missing quantities and the negative-score
    pace-mapping convention. ``userdata.pulse_ep`` records the source kinds
    and encoding, because OpenEP's positional activation slot carries either
    activation times or negative pace scores.
    """
    vertices = np.empty((0, 3)) if epmap.vertices is None else np.asarray(epmap.vertices, float)
    triangles = (
        np.empty((0, 3), dtype=np.int64)
        if epmap.triangles is None
        else np.asarray(epmap.triangles, dtype=np.int64) + 1  # 0-based -> MATLAB
    )
    surface, surface_notes = surface_arrays(epmap)
    maps, map_notes = signal_maps(epmap)
    surface_notes.extend(map_notes)
    electric, electric_notes = electric_arrays(epmap)
    # Older imports and direct callers may supply study-level windows. Point
    # numbers alone do not identify a CARTO recording across different maps.
    selected_force = [
        wave
        for wave in (force_windows or [])
        if not wave.meta.get("map_name") or wave.meta["map_name"] == epmap.map_name
    ]
    force, force_notes = force_for_points(list(epmap.measurement_points or []), selected_force)
    electric["force"] = force
    electric_notes.extend(force_notes)
    points = list(epmap.measurement_points or [])
    signal_metadata = {"included": False, "points_with_bipolar": 0}
    if signal_windows is not None:
        from pulse_ep.core.openep_signals import signal_arrays

        signals, signal_metadata, notes = signal_arrays(
            epmap, signal_windows, ecg_channels, signal_scale_to_mv
        )
        electric.update(signals)
        electric_notes.extend(notes)
    # OpenEP interprets annotations as samples. For maps without waveforms,
    # use a declared 1000-Hz encoding (one millisecond per unit), not a claim
    # about the acquisition's unknown sampling frequency.
    rate = electric.get("sampleFrequency", 1000.0)
    lat_ms = np.array([_measure(p, ACTIVATION_TIME) for p in points])
    reconstructed = 0
    for i, point in enumerate(points):
        annotation = point.annotations or {}
        if annotation.get("annotation_unit") != "ms":
            continue
        ref = signal_metadata.get("reference_samples", np.full(len(points), np.nan))[i]
        if not np.isfinite(ref):
            ref = 0.0
            reconstructed += 1
        electric["annotations"]["referenceAnnot"][i] = ref
        electric["annotations"]["mapAnnot"][i] = ref + lat_ms[i] * rate / 1000
        electric["annotations"]["woi"][i] *= rate / 1000
        if _point_activation_kind(point, _surface_activation_kind(epmap)) == PACEMAP_SCORE:
            electric["annotations"]["mapAnnot"][i] = ref - abs(_measure(point, PACEMAP_SCORE))
    if reconstructed:
        electric_notes.append(
            f"annotations: {reconstructed} points use a zero origin to encode LAT; no waveform-aligned reference sample available"
        )
    if "sampleFrequency" not in electric:
        electric["sampleFrequency"] = 1000.0

    ablation_metadata = {}
    rfindex = None
    if ablation_points is not None:
        from pulse_ep.core.openep_ablation import ablation_arrays

        rfindex, ablation_metadata, notes = ablation_arrays(ablation_points)
        electric_notes.extend(notes)

    rim = epmap.is_vertex_at_edge
    activation_kind = _surface_activation_kind(epmap)
    return {
        "systemName": {"ensite": "ensitex"}.get(system_name, system_name or ""),
        "pulse_ep": {
            "surface_activation_kind": activation_kind,
            "surface_activation_encoding": (
                "negative_score" if activation_kind == PACEMAP_SCORE else "identity"
            ),
            "surface_activation_unit": "%" if activation_kind == PACEMAP_SCORE else "ms",
            "point_activation_kinds": [
                _point_activation_kind(point, activation_kind)
                for point in (epmap.measurement_points or [])
            ],
            "lat_ms": lat_ms,
            "signals": signal_metadata,
            "ablation": ablation_metadata,
            "annotation_frequency_is_encoding": "sample_counts" not in signal_metadata,
        },
        "surface": {
            "triRep": {"X": vertices, "Triangulation": triangles},
            "isVertexAtRim": (
                np.zeros(len(vertices), dtype=bool) if rim is None else np.asarray(rim, dtype=bool)
            ),
            "normals": (
                np.empty((0, 3)) if epmap.normals is None else np.asarray(epmap.normals, float)
            ),
            "signalMaps": maps,
            **surface,
        },
        "electric": electric,
        # Summary RF markers are available in rfindex after explicit selection.
        # Manual RF time-series are not inferred from those summary records.
        "rf": {},
        **({"rfindex": rfindex} if rfindex is not None else {}),
        "notes": [
            f"written by pulse-ep from map {epmap.map_name!r}"
            + (f" of study {study_name!r}" if study_name else ""),
            *surface_notes,
            *electric_notes,
        ],
    }


def write_userdata(
    epmap: EPMap,
    path,
    study_name: str | None = None,
    force_windows: list | None = None,
    system_name: str | None = None,
    **options,
) -> list[str]:
    """Write ``userdata`` to a MATLAB ``.mat`` file; return its notes.

    The notes are returned as well as written, so a caller sees what the
    structure could not carry without opening MATLAB.
    """
    userdata = to_userdata(
        epmap,
        study_name=study_name,
        force_windows=force_windows,
        system_name=system_name,
        **options,
    )
    return write_userdata_payload(userdata, path)


def write_userdata_payload(userdata: dict, path) -> list[str]:
    """Serialize an already selected export (also used by the CLI)."""
    from scipy.io import savemat

    # MATLAB's triangulation constructor requires double connectivity, even
    # though its entries represent integral 1-based vertex indices.
    tr = userdata["surface"]["triRep"]
    tr["Triangulation"] = tr["Triangulation"].astype(float)

    # Plain Python string lists become MATLAB character matrices. OpenEP's
    # getNumPts counts numel(names), so that would count characters, not points.
    # Use one cell per point, also for variable-length tag lists and property names.
    def cells(values):
        result = np.empty((len(values), 1), dtype=object)
        for i, value in enumerate(values):
            result[i, 0] = value
        return result

    electric = userdata["electric"]
    electric["names"] = cells(electric["names"])
    electric["tags"] = cells([cells(tags) for tags in electric["tags"]])
    electric["electrodeNames_bip"] = cells(electric["electrodeNames_bip"])
    if "electrodeNames_uni" in electric:
        electric["electrodeNames_uni"] = np.asarray(electric["electrodeNames_uni"], dtype=object)
    if "ecgNames" in electric:
        electric["ecgNames"] = cells(electric["ecgNames"])
    for prop in electric["signalProps"]:
        prop["name"] = cells(prop["name"])
    savemat(str(path), {"userdata": userdata}, long_field_names=True, oned_as="column")
    return userdata["notes"]
