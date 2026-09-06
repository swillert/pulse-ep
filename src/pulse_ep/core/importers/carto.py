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
from pulse_ep.core.importers.plan import ImportPlan, MapPlan, StudyPlan
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    PACEMAP_SCORE,
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


def register_carto_scalars(epmap, act_bip: np.ndarray | None) -> None:
    """Register CARTO's per-vertex scalars as vendor-neutral fields.

    Decodes the overloaded primary slot (see :func:`classify_primary_scalar`)
    and the bipolar voltage, registering both **under the name of the quantity
    they hold** — the same names EnSiteX uses, so one query spans both vendors.

    These used to be ``"act"`` and ``"vol"``: CARTO's own spelling, which no
    EnSiteX map answers to. The old names still resolve through
    ``EPMap.get_scalar`` for studies imported before this change.
    """
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


def carto_points_to_measurements(point_dicts: list[dict]) -> list[MeasurementPoint]:
    """Convert :func:`~pulse_ep.core.point_importer.import_map_points` output
    into vendor-neutral :class:`MeasurementPoint` objects.

    CARTO's per-point data was already parsed — it just stopped at the
    fixed-column ``EPMapPointModel``, so nothing downstream could compare it
    with an EnSiteX point set. This is a conversion, not a new parser: the
    legacy rows are still written, and keep the raw WOI and annotation
    components this vendor-neutral view derives from.

    Activation time follows CARTO's convention
    ``Map_Annotation - Reference_Annotation``, and is only set when both are
    present. Catheter positions arrive as a flat ``[x1,y1,z1, x2,y2,z2, …]``
    list per connector and become one labelled electrode each (``CS_1``, …).
    """
    points: list[MeasurementPoint] = []
    for pd in point_dicts:
        x, y, z = pd.get("position_x"), pd.get("position_y"), pd.get("position_z")
        if x is None or y is None or z is None:
            continue
        point = MeasurementPoint(
            position=np.array([x, y, z], dtype=float),
            index=pd.get("point_index"),
            source_id=None if pd.get("carto_point_id") is None else str(pd["carto_point_id"]),
        )

        bip, uni = pd.get("bipolar_voltage"), pd.get("unipolar_voltage")
        if bip is not None:
            point.add(field_name(VOLTAGE_BIPOLAR), float(bip), VOLTAGE_BIPOLAR)
        if uni is not None:
            point.add(field_name(VOLTAGE_UNIPOLAR), float(uni), VOLTAGE_UNIPOLAR)

        ref, map_ann = pd.get("reference_annotation"), pd.get("map_annotation")
        if ref is not None and map_ann is not None:
            point.add(field_name(ACTIVATION_TIME), float(map_ann) - float(ref), ACTIVATION_TIME)

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


def populate_carto_mesh(epmap, mesh_file: str) -> None:
    """Read a CARTO ``.mesh`` file into ``epmap`` (geometry + scalar fields).

    Replaces the former ``EPMap.process_carto_mesh_file`` — mesh parsing is a
    vendor concern and lives in the importer, not on the domain object. The
    legacy ``act_bip`` array is still populated for figure/tag consumers.
    """
    from pulse_ep.core import mesh_proc

    triangles, vertices, triangle_areas, is_edge, act_bip, normals, uni_imp_frc = (
        mesh_proc.read_carto_mesh_file(mesh_file)
    )
    epmap.triangles = triangles
    epmap.vertices = vertices
    epmap.triangle_areas = triangle_areas
    epmap.is_vertex_at_edge = is_edge
    epmap.act_bip = act_bip  # legacy storage (figures / tag_maps read this)
    epmap.normals = normals
    epmap.uni_imp_frc = uni_imp_frc
    register_carto_scalars(epmap, act_bip)


class CartoImporter:
    """Vendor importer for CARTO 3 (Biosense Webster) exports."""

    name = "carto"

    def sniff(self, source: ImportSource) -> bool:
        # CARTO exports carry per-map ``.mesh`` files; EnSiteX uses DIF XML
        # and has none — a clean discriminator without parsing anything.
        return bool(source.list("*.mesh"))

    def prepare(self, source: ImportSource) -> ImportPlan:
        """Propose what would be imported, reading only the study XMLs.

        Cheap by design: map names and point counts come from the study
        catalogue, so no mesh is touched until :meth:`commit`.
        """
        from pulse_ep.core.importer import discover_carto_exports, extract_subfolder
        from pulse_ep.core.xml_proc import get_maps, get_study_name, process_xml

        root = source.materialize(source.list("*.xml"))
        studies: list[StudyPlan] = []
        issues: list[str] = []
        for xml in discover_carto_exports(root):
            try:
                tree = process_xml(xml)
                _n, names, n_points, mesh_files = get_maps(tree)
                study_name = f"{extract_subfolder(xml, 4)}-{get_study_name(tree)}"
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
            studies.append(StudyPlan(study_name=study_name, vendor=self.name, maps=maps))
        return ImportPlan(studies=studies, issues=issues)

    def commit(self, plan: ImportPlan, source: ImportSource) -> list[Study]:
        """Import the maps the reviewer kept."""
        selected = {
            m.map_name for sp in plan.studies for m in sp.maps if m.include and sp.maps is not None
        }
        # ``import_carto`` filters by regex over map names; anchor an exact
        # alternation of the selection so no unselected map slips through.
        map_filter = (
            "^(?:" + "|".join(re.escape(n) for n in sorted(selected)) + ")$" if selected else None
        )
        return self._parse(source, map_filter)

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
