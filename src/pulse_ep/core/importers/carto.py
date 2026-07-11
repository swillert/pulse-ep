"""CARTO 3 (Biosense Webster) decode helpers.

CARTO overloads the "primary" per-vertex scalar slot (historically
``act_bip[:, 0]``): it holds either activation time or a pace-mapping
correlation, distinguished only by convention. :func:`classify_primary_scalar`
resolves that overload once, at import, and hands the core layer a clean,
labelled :class:`ScalarField`-ready ``(kind, values)`` pair.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.base import register_importer
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.scalar_field import ACTIVATION_TIME, PACEMAP_SCORE, VOLTAGE_BIPOLAR
from pulse_ep.core.study import Study

#: CARTO marks "no valid datum" vertices with this sentinel; values at or
#: above it are not real measurements.
CARTO_SENTINEL = 10000.0


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
    into ``"act"`` (kind ``activation_time`` or ``pacemap_score``) and the
    bipolar voltage into ``"vol"``. Called at import so the core never needs
    to know these come from CARTO.
    """
    if act_bip is None:
        return
    kind, primary = classify_primary_scalar(act_bip[:, 0])
    epmap.register_scalar("act", primary, kind=kind)
    epmap.register_scalar("vol", act_bip[:, 1], kind=VOLTAGE_BIPOLAR)


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

    def parse(self, source: ImportSource) -> list[Study]:
        # The existing readers are path-based, so make the data local first
        # (a directory is returned as-is; a ZIP/upload is extracted to temp).
        from pulse_ep.core.importer import discover_carto_exports, import_studies

        root = source.materialize()
        study_xmls = discover_carto_exports(root)
        studies = import_studies(study_xmls) if study_xmls else []
        studies = [s for s in studies if s is not None]
        for study in studies:
            study.vendor = "carto"
        return studies


register_importer(CartoImporter())
