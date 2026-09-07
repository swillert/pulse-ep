"""CARTO 3 (Biosense Webster) decode helpers.

CARTO overloads the "primary" per-vertex scalar slot (historically
``act_bip[:, 0]``): it holds either activation time or a pace-mapping
correlation, distinguished only by convention. :func:`classify_primary_scalar`
resolves that overload once, at import, and hands the core layer a clean,
labelled :class:`ScalarField`-ready ``(kind, values)`` pair.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from pulse_ep.core.importers.base import register_importer
from pulse_ep.core.importers.lexicon import CARTO_MESH_COLORS, resolve
from pulse_ep.core.importers.plan import ImportPlan, MapPlan, StudyPlan, WaveformPlan
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.placed_point import ABLATION, PlacedPoint
from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    PACEMAP_SCORE,
    UNKNOWN,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
    field_name,
)
from pulse_ep.core.study import Study

#: CARTO marks "no valid datum" vertices with this sentinel; values at or
#: above it are not real measurements.
CARTO_SENTINEL = 10000.0

#: CARTO's importer ignores maps below this point count as not clinically useful.
_MIN_MAP_POINTS = 5

#: Provenance tag on every field this importer registers; the mesh column it
#: came from is appended (``carto:LAT``, ``carto:Paso``).
CARTO_SOURCE = "carto"

#: The overloaded per-vertex column, whose decode also settles what the
#: per-point annotation difference holds. See :func:`point_primary_kind`.
CARTO_PRIMARY_COLUMN = "LAT"


def classify_primary_scalar(values: np.ndarray) -> tuple[str, np.ndarray]:
    """Decode CARTO's overloaded primary scalar slot.

    Rule (matching the existing ``tag_maps.data_is_pacemapping`` heuristic):
    export sentinels (``>= CARTO_SENTINEL``) are masked to ``NaN``; a field
    whose valid values are *entirely negative* is a pace-mapping correlation
    stored with negative sign — it is flipped to a positive ``0..100 %`` scale
    and labelled :data:`PACEMAP_SCORE`. Any other field (positive, or mixed
    sign as a signed activation map would be) is :data:`ACTIVATION_TIME`.

    :returns: ``(kind, conditioned_values)`` ready for
        :meth:`EPMap.register_scalar`.
    """
    v = np.asarray(values, dtype=float).copy()
    v[v >= CARTO_SENTINEL] = np.nan

    finite = v[~np.isnan(v)]
    if finite.size and np.nanmax(finite) < 0:
        # entirely-negative → pace-mapping stored with negative sign
        return PACEMAP_SCORE, -v
    return ACTIVATION_TIME, v


def _mask_sentinels(values: np.ndarray) -> np.ndarray:
    """A copy with CARTO's "no valid datum" markers replaced by ``NaN``."""
    v = np.asarray(values, dtype=float).copy()
    v[v >= CARTO_SENTINEL] = np.nan
    return v


def _register_unique(epmap, name: str, values: np.ndarray, kind: str, token: str) -> None:
    """Register a field, keeping the vendor token when the name is taken.

    Two columns can decode to the same quantity — a map whose ``LAT`` slot
    holds a pace-match score *and* carries a ``Paso`` column. Overwriting
    would lose one of them silently; the loser keeps its raw CARTO name.
    """
    if name in epmap.scalar_fields:
        name = token
    # The source records *which column* this came from, not just the vendor.
    # It is what lets a later reader tell a pace-match score decoded out of the
    # overloaded ``LAT`` slot from one the export stated in its own ``Paso``
    # column — a distinction the field name alone cannot carry, since both are
    # called ``pacemap_score``.
    epmap.register_scalar(name, values, kind=kind, source=f"{CARTO_SOURCE}:{token}")


def register_carto_mesh_scalars(epmap, colors: dict, attributes: dict | None = None) -> None:
    """Register the **named** per-vertex columns of a CARTO mesh.

    The mesh file declares what each column holds (``Unipolar``, ``LAT``,
    ``Force``, ``Paso``, ``µBi`` …); :data:`CARTO_MESH_COLORS` maps the names
    this project understands to quantities and everything else imports under
    its raw CARTO token. Columns holding no valid datum at all — most exports
    fill only three or four of thirteen — are skipped, so a map advertises the
    quantities it actually measured.

    ``LAT`` keeps its sign-based decode (see :func:`classify_primary_scalar`):
    the slot really does hold either an activation time or a pace-match score.
    """

    # Columns whose quantity is decided by inspecting values (the LAT slot)
    # are registered last, so a column that *declares* what it holds always
    # wins the name: an export with a filled ``Paso`` column states its
    # pace-match score, while a negative-looking LAT slot only implies one.
    def _decoded_by_sign(item) -> bool:
        return resolve(CARTO_MESH_COLORS, item[0]) == ACTIVATION_TIME

    for token, raw in sorted(colors.items(), key=_decoded_by_sign):
        values = _mask_sentinels(raw)
        if not np.isfinite(values).any():
            continue  # column present but empty — every value a sentinel

        kind = resolve(CARTO_MESH_COLORS, token)
        if kind == ACTIVATION_TIME:
            kind, values = classify_primary_scalar(values)
        elif kind == PACEMAP_SCORE:
            finite = values[np.isfinite(values)]
            if finite.size and finite.max() < 0:
                values = -values  # same negative-sign convention as the LAT slot
        _register_unique(epmap, field_name(kind, token), values, kind, token)

    # Per-vertex flags (EML / extEML / SCAR): a marked region, not a
    # measurement. Registered only where something is actually marked, so an
    # all-zero column does not pose as data.
    for token, raw in (attributes or {}).items():
        values = np.asarray(raw, dtype=float)
        if not np.any(values > 0):
            continue
        _register_unique(epmap, field_name(UNKNOWN, token), values, UNKNOWN, token)


def register_carto_scalars(
    epmap,
    act_bip: np.ndarray | None,
    colors: dict | None = None,
    attributes: dict | None = None,
) -> None:
    """Register CARTO's per-vertex scalars as vendor-neutral fields.

    With ``colors`` (the mesh's named columns) this defers to
    :func:`register_carto_mesh_scalars`. Without them it falls back to the
    historical two-column decode: the overloaded primary slot (see
    :func:`classify_primary_scalar`) plus the bipolar voltage, registered
    **under the name of the quantity they hold** — the same names EnSite X
    uses, so one query spans both vendors.

    These used to be ``"act"`` and ``"vol"``: CARTO's own spelling, which no
    EnSite X map answers to. The old names still resolve through
    ``EPMap.get_scalar`` for studies imported before this change.
    """
    if colors:
        register_carto_mesh_scalars(epmap, colors, attributes)
        return
    if act_bip is None:
        return
    kind, primary = classify_primary_scalar(act_bip[:, 0])
    epmap.register_scalar(field_name(kind), primary, kind=kind)
    epmap.register_scalar(field_name(VOLTAGE_BIPOLAR), act_bip[:, 1], kind=VOLTAGE_BIPOLAR)


#: How a CARTO connector's electrode array is labelled on a measurement point.
_ELECTRODE_LABELS = {
    "cs_positions": "CS",
    "magnetic20_positions": "20A",
    "roving_positions": "ROV",
}


#: A pace-match score is a percentage; anything outside this range in the
#: annotation slot of a pace map is an annotation of another kind (a point
#: taken in activation mode, a late-marked reference) and not a score.
_PACEMAP_SCORE_RANGE = (0.0, 100.0)


def point_primary_kind(epmap) -> str | None:
    """What a map's per-point annotation difference holds, judged by the mesh.

    CARTO writes the same overloaded quantity per point that it writes per
    vertex: ``Map_Annotation - Reference_Annotation`` is an activation time on
    an activation map and the pace-match score on a pace map (with the
    negative sign of the mesh's ``LAT`` slot). The mesh has already been
    decoded by :func:`classify_primary_scalar`, so the points follow it:
    :data:`PACEMAP_SCORE` when the map carries a field of that kind,
    :data:`ACTIVATION_TIME` when it carries one of that kind, ``None`` (decide
    from the points themselves) when it carries neither.
    """
    fields = getattr(epmap, "scalar_fields", None)
    if not fields:
        return None

    # The per-point difference is the counterpart of *one* column — the
    # overloaded ``LAT`` slot — so the question is what that slot was decoded
    # into, not which quantities the map carries anywhere. A map can hold both:
    # an activation map whose export also filled ``Paso`` registers
    # ``activation_time`` (from LAT) beside ``pacemap_score`` (from Paso), and
    # reading "carries a pace-match field" as "its points are scores" turns
    # every activation time on such a map into a percentage.
    primary = f"{CARTO_SOURCE}:{CARTO_PRIMARY_COLUMN}"
    for field in fields.values():
        if field.source == primary:
            return field.kind if field.kind in (PACEMAP_SCORE, ACTIVATION_TIME) else None

    # No column provenance: a map imported through the legacy two-column path,
    # where the primary slot is the only source of either quantity.
    field_of_kind = getattr(epmap, "field_of_kind", None)
    if field_of_kind is None:
        return None
    if field_of_kind(PACEMAP_SCORE) is not None:
        return PACEMAP_SCORE
    if field_of_kind(ACTIVATION_TIME) is not None:
        return ACTIVATION_TIME
    return None


def decode_point_annotations(
    point_dicts: list[dict], primary_kind: str | None = None
) -> tuple[str, list[float | None]]:
    """Decode ``Map_Annotation - Reference_Annotation`` for a map's points.

    The difference is CARTO's per-point counterpart of the mesh's overloaded
    ``LAT`` slot: an activation time (ms) on an activation map, the pace-match
    score on a pace map, stored with a negative sign as on the mesh — and, as
    on the mesh, ``-10000`` where there is no datum (the reference point of a
    pace map, whose own beat is never scored). Before this the difference was
    always labelled ``activation_time``, so every pace map carried thousands of
    "activation times" of -50 … -100 ms and a few of -10000.

    ``primary_kind`` is the mesh's verdict (:func:`point_primary_kind`); with
    ``None`` the points decide for themselves by the mesh's own rule — all
    valid values negative means a pace map. On a pace map a value is a score
    only if its magnitude is a percentage: a point annotated in another mode
    (-196, 30) is reported as missing rather than as a score.

    :returns: ``(kind, values)`` with one entry per point, ``None`` where the
        point has no usable value.
    """
    raw: list[float | None] = []
    for pd in point_dicts:
        ref, map_ann = pd.get("reference_annotation"), pd.get("map_annotation")
        if ref is None or map_ann is None:
            raw.append(None)
            continue
        diff = float(map_ann) - float(ref)
        raw.append(None if abs(diff) >= CARTO_SENTINEL else diff)

    kind = primary_kind
    if kind is None:
        valid = [v for v in raw if v is not None]
        kind = PACEMAP_SCORE if valid and max(valid) < 0 else ACTIVATION_TIME
    if kind != PACEMAP_SCORE:
        return ACTIVATION_TIME, raw

    lo, hi = _PACEMAP_SCORE_RANGE
    scores: list[float | None] = []
    negative = any(v is not None and v < 0 for v in raw)
    for v in raw:
        if v is None:
            scores.append(None)
            continue
        # The mesh convention decides the sign: on a negative-signed map a
        # positive value is not a score, on a positive-signed export it is.
        if negative and v > 0:
            scores.append(None)
            continue
        score = abs(v)
        scores.append(score if lo <= score <= hi else None)
    return PACEMAP_SCORE, scores


#: Point-export field -> the key it takes on :attr:`MeasurementPoint.annotations`.
#: The target names are the ones a stored waveform records for the same point
#: (see :func:`~pulse_ep.core.importers.carto_signal.parse_point_export`), so a
#: window and its point describe themselves identically.
_ANNOTATION_FIELDS = {
    "start_time": "start_time",
    "reference_annotation": "reference",
    "map_annotation": "map",
    "woi_from": "woi_from",
    "woi_to": "woi_to",
}


def point_annotations(pd: dict) -> dict:
    """Where a point's beat sits in the signal recorded for it.

    The components the activation time (or pace-match score) is *derived*
    from, kept beside the derived value: without them a stored 2.5 s window is
    2500 samples with no landmark in it, and until now they survived only in
    the legacy ``ep_map_points`` table — which the queue and review-UI import
    path never writes, and which no EnSite X study has at all.

    A field the export does not carry is left out rather than stored as null:
    absent means "not exported", the same as for a measurement. CARTO's
    ``-10000`` no-datum marker is dropped for the same reason.
    """
    annotations = {}
    for source, key in _ANNOTATION_FIELDS.items():
        value = pd.get(source)
        if value is None:
            continue
        value = float(value)
        if abs(value) >= CARTO_SENTINEL and key in ("reference", "map"):
            continue  # the unscored reference beat carries no annotation
        annotations[key] = int(value) if value.is_integer() else value
    return annotations


def carto_points_to_measurements(
    point_dicts: list[dict], primary_kind: str | None = None
) -> list[MeasurementPoint]:
    """Convert :func:`~pulse_ep.core.point_importer.import_map_points` output
    into vendor-neutral :class:`MeasurementPoint` objects.

    CARTO's per-point data was already parsed — it just stopped at the
    fixed-column ``EPMapPointModel``, so nothing downstream could compare it
    with an EnSite X point set. This is a conversion, not a new parser: the
    legacy rows are still written, and the raw WOI and annotation components
    travel on the neutral point as ``annotations`` (see
    :func:`point_annotations`), so they no longer depend on that CARTO-shaped
    table — which only the CLI writes at all.

    The annotation difference ``Map_Annotation - Reference_Annotation`` is an
    activation time on an activation map and the pace-match score on a pace
    map — decoded by :func:`decode_point_annotations`, following the mesh
    (``primary_kind``) — and is only set when both annotations are present and
    hold a datum. Catheter positions arrive as a flat ``[x1,y1,z1, x2,y2,z2, …]``
    list per connector and become one labelled electrode each (``CS_1``, …).
    Tags (``pd["tags"]``, names resolved by the caller) are carried as they are.
    """
    kind, values = decode_point_annotations(point_dicts, primary_kind)
    points: list[MeasurementPoint] = []
    for pd, value in zip(point_dicts, values, strict=True):
        x, y, z = pd.get("position_x"), pd.get("position_y"), pd.get("position_z")
        if x is None or y is None or z is None:
            continue
        point = MeasurementPoint(
            position=np.array([x, y, z], dtype=float),
            index=pd.get("point_index"),
            source_id=None if pd.get("carto_point_id") is None else str(pd["carto_point_id"]),
            tags=[str(t) for t in (pd.get("tags") or [])],
            annotations=point_annotations(pd),
        )

        bip, uni = pd.get("bipolar_voltage"), pd.get("unipolar_voltage")
        if bip is not None:
            point.add(field_name(VOLTAGE_BIPOLAR), float(bip), VOLTAGE_BIPOLAR)
        if uni is not None:
            point.add(field_name(VOLTAGE_UNIPOLAR), float(uni), VOLTAGE_UNIPOLAR)

        if value is not None:
            point.add(field_name(kind), float(value), kind)

        for key, label in _ELECTRODE_LABELS.items():
            coords = pd.get(key)
            if not coords:
                continue
            arr = np.asarray(coords, dtype=float)
            if arr.size < 3:
                continue
            for i, xyz in enumerate(arr[: arr.size - arr.size % 3].reshape(-1, 3), start=1):
                point.electrodes[f"{label}_{i}"] = xyz

        points.append(point)
    return points


def _is_study_catalogue(path: str) -> bool:
    """True if this XML is a study catalogue (``<Study>``), not a point export."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(2048)
    except OSError:
        return False
    return b"<Study" in head


# --- VisiTag ablation sites (UNVERIFIED — see the warning below) ------------

#: Column name -> the ``PlacedPoint.attributes`` key it becomes. Matching is by
#: *name*, case- and separator-insensitive, never by position: VisiTag's column
#: set differs between CARTO versions, so a positional reader would silently
#: mis-assign values. A column not listed here is still kept, under its own
#: name, so nothing is lost.
_VISITAG_ATTRS: dict[str, str] = {
    "duration": "duration_s",
    "durationtime": "duration_s",
    "averageforce": "average_force_g",
    "avgforce": "average_force_g",
    "fti": "force_time_integral",
    "maxtemperature": "max_temperature_c",
    "maxpower": "max_power_w",
    "baseimpedance": "base_impedance_ohm",
    "impedancedrop": "impedance_drop_ohm",
    "rfindex": "rf_index",
    "ablationindex": "ablation_index",
    "lesionindex": "lesion_index",
    "session": "session",
    "sessionindex": "session",
    "channelid": "channel_id",
    "tagindex": "tag_index",
    "siteindex": "tag_index",
    "timestamp": "timestamp",
}

_VISITAG_POSITION = {"x": 0, "y": 1, "z": 2}


def _norm_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _numeric(text: str):
    """``"7"`` -> 7, ``"22.5"`` -> 22.5, anything else unchanged.

    Indices and session numbers stay integers so an identifier built from
    one reads as ``"7"`` rather than ``"7.0"``.
    """
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_carto_visitag_sites(data: bytes | str, name: str = "") -> list[PlacedPoint]:
    """Parse a VisiTag ``Sites.txt`` into ablation :class:`PlacedPoint` objects.

    .. warning::

       **UNVERIFIED — no VisiTag export has been available to test against.**

       This parser is written from the documented VisiTag layout: a
       tab-separated table with a header row, one row per ablation site,
       carrying ``X``/``Y``/``Z`` plus RF parameters. It is deliberately
       **column-name driven**: an unexpected column set yields fewer
       attributes, never values assigned to the wrong quantity, and a file
       without recognisable X/Y/Z columns yields no points at all rather than
       nonsense. Unrecognised columns are preserved under their own names.

       Confirm against a real VisiTag export before trusting the ablation
       sites it produces, and delete this warning once that is done.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    def cells(line: str) -> list[str]:
        # VisiTag is tab-separated, but whitespace-padded columns are common.
        return [c.strip() for c in (line.split("\t") if "\t" in line else line.split())]

    header = cells(lines[0])
    norm = [_norm_column(h) for h in header]
    pos_idx = {axis: norm.index(axis) for axis in _VISITAG_POSITION if axis in norm}
    if len(pos_idx) < 3:
        return []  # no coordinates -> not a sites table; do not guess

    points: list[PlacedPoint] = []
    for i, line in enumerate(lines[1:]):
        f = cells(line)
        if len(f) < len(pos_idx):
            continue
        try:
            position = np.array(
                [float(f[pos_idx["x"]]), float(f[pos_idx["y"]]), float(f[pos_idx["z"]])],
                dtype=float,
            )
        except (ValueError, IndexError):
            continue

        attributes: dict = {}
        for j, raw in enumerate(header):
            key = _norm_column(raw)
            if key in _VISITAG_POSITION or j >= len(f) or not f[j]:
                continue
            attributes[_VISITAG_ATTRS.get(key, raw)] = _numeric(f[j])

        points.append(
            PlacedPoint(
                type=ABLATION,
                position=position,
                label=None,
                attributes=attributes,
                source_id=str(attributes.get("tag_index") or i),
            )
        )
    return points


#: Where VisiTag sites live in an export. CARTO writes them into a
#: ``VisiTagExport`` folder; the glob stays loose because the folder is an
#: optional, separately-selected part of an export.
_VISITAG_GLOBS = ("*VisiTag*/*Sites*.txt", "*VisiTagExport*/*.txt", "*Sites.txt")


def _visitag_files(source: ImportSource) -> list[str]:
    """VisiTag site tables present in the export, if any."""
    seen = {n for g in _VISITAG_GLOBS for n in source.list(g)}
    return sorted(n for n in seen if "site" in Path(n).name.lower())


def _waveform_plan(source: ImportSource, map_names: list[str]) -> WaveformPlan:
    """The study's per-point ECG windows, proposed but **not** selected.

    Opt-in for the same reason EnSite X waveforms are: CARTO writes one 2.5 s
    window of every channel per acquired point, so a few thousand points are
    several gigabytes — more than the rest of the export put together.

    An ECG file is named ``<map name>_ECG_Export_<timestamp>.txt``, so the
    study's own maps select its files. An export whose files match no map name
    keeps all of them: better a reviewer sees too many than a study silently
    offers no signals at all.
    """
    from pulse_ep.core.importers.carto_signal import ecg_files

    files = ecg_files(source)
    prefixes = tuple(f"{name}_ECG_Export_" for name in map_names)
    mine = [f for f in files if Path(f).name.startswith(prefixes)] if prefixes else []
    if not mine:
        mine = files
    return WaveformPlan(
        files=mine,
        estimated_bytes=sum(source.size(name) for name in mine),
        include=False,
    )


def populate_carto_mesh(epmap, mesh_file: str) -> None:
    """Read a CARTO ``.mesh`` file into ``epmap`` (geometry + scalar fields).

    Replaces the former ``EPMap.process_carto_mesh_file`` — mesh parsing is a
    vendor concern and lives in the importer, not on the domain object. The
    legacy ``act_bip`` array is still populated for figure/tag consumers.
    """
    from pulse_ep.core import mesh_proc

    mesh = mesh_proc.parse_carto_mesh(mesh_file)
    epmap.triangles = mesh.triangles
    epmap.vertices = mesh.vertices
    epmap.triangle_areas = mesh.triangle_areas
    epmap.is_vertex_at_edge = mesh.is_vertex_at_edge
    epmap.act_bip = mesh.act_bip  # legacy storage (figures / tag_maps read this)
    epmap.normals = mesh.normals
    epmap.uni_imp_frc = mesh.uni_imp_frc
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors, attributes=mesh.attributes)


class CartoImporter:
    """Vendor importer for CARTO 3 (Biosense Webster) exports."""

    name = "carto"

    def sniff(self, source: ImportSource) -> bool:
        # CARTO exports carry per-map ``.mesh`` files; EnSite X uses DIF XML
        # and has none — a clean discriminator without parsing anything.
        return bool(source.list("*.mesh"))

    def prepare(self, source: ImportSource) -> ImportPlan:
        """Propose what would be imported, reading only the study XMLs.

        Cheap by design: map names and point counts come from the study
        catalogue, so no mesh is touched until :meth:`commit`.
        """
        from pulse_ep.core.importer import discover_carto_exports, study_name_for
        from pulse_ep.core.xml_proc import get_maps, get_study_name, process_xml

        root = source.materialize(source.list("*.xml"))
        studies: list[StudyPlan] = []
        issues: list[str] = []
        for xml in discover_carto_exports(root):
            # An export holds one study catalogue among thousands of per-point
            # XMLs. Skip the others by content rather than reporting each as a
            # failure — a real export would drown the plan in ~2000 issues.
            if not _is_study_catalogue(xml):
                continue
            try:
                tree = process_xml(xml)
                _n, names, n_points, mesh_files = get_maps(tree)
                study_name = study_name_for(xml, get_study_name(tree))
            except Exception as exc:  # not a study catalogue, or unreadable
                issues.append(f"{Path(xml).name}: {exc}")
                continue
            if not names:
                continue
            maps = [
                MapPlan(
                    map_name=name,
                    files=[mesh] if mesh else [],
                    # CARTO's own importer skips maps with fewer than 5 points
                    include=count >= _MIN_MAP_POINTS,
                    issues=([] if count >= _MIN_MAP_POINTS else [f"only {count} points — skipped"]),
                )
                for name, count, mesh in zip(names, n_points, mesh_files)  # noqa: B905
            ]
            visitag = _visitag_files(source)
            if visitag:
                issues.append(
                    "VisiTag ablation sites found — the parser for them is UNVERIFIED "
                    "(never tested against a real VisiTag export); check the imported "
                    "sites before relying on them"
                )
            studies.append(
                StudyPlan(
                    study_name=study_name,
                    vendor=self.name,
                    maps=maps,
                    placed_point_files=visitag,
                    waveforms=_waveform_plan(source, names),
                )
            )
        return ImportPlan(studies=studies, issues=issues)

    def commit(self, plan: ImportPlan, source: ImportSource) -> list[Study]:
        """Import the maps the reviewer kept, plus any VisiTag ablation sites."""
        selected = {m.map_name for sp in plan.studies for m in sp.maps if m.include}
        # ``import_carto`` filters by regex over map names; anchor an exact
        # alternation of the selection so no unselected map slips through.
        map_filter = (
            "^(?:" + "|".join(re.escape(n) for n in sorted(selected)) + ")$" if selected else None
        )
        decoded = self._parse(source, map_filter) if selected else []
        by_name = {study.name: study for study in decoded}
        result = []
        for sp in plan.studies:
            study = by_name.get(sp.study_name)
            if study is None:
                study = Study(sp.study_name, vendor=self.name, provenance=sp.provenance)
            # The legacy regex is case-insensitive and shared by all studies.
            # Apply the actual selections to each study after decoding too.
            wanted = {m.map_name: m for m in sp.maps if m.include}
            study.epmaps = [m for m in study.epmaps if m.map_name in wanted]
            for epmap in study.epmaps:
                if not wanted[epmap.map_name].include_points:
                    epmap.measurement_points = []
                    for attr in (
                        "xyz",
                        "woi",
                        "reference_annotation",
                        "map_annotation",
                        "unipolar",
                        "bipolar",
                        "impedance_time",
                        "impedance_value",
                    ):
                        setattr(epmap, attr, None)
            if sp.include_placed_points:
                for f in sp.placed_point_files:
                    study.placed_points += parse_carto_visitag_sites(source.open(f).read(), name=f)
            if study.epmaps or study.placed_points:
                result.append(study)
        return result

    def parse(self, source: ImportSource) -> list[Study]:
        return self._parse(source, None)

    def _parse(self, source: ImportSource, map_filter: str | None) -> list[Study]:
        # The existing readers are path-based, so make the data local first
        # (a directory is returned as-is; a ZIP/upload is extracted to temp).
        from pulse_ep.core.importer import discover_carto_exports, import_studies

        root = source.materialize()
        study_xmls = discover_carto_exports(root)
        studies = import_studies(study_xmls, map_filter=map_filter) if study_xmls else []
        studies = [s for s in studies if s is not None]
        for study in studies:
            study.vendor = "carto"
        return studies


register_importer(CartoImporter())
