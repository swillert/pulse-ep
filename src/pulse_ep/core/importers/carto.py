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
from pulse_ep.core.scalar_field import ACTIVATION_TIME, PACEMAP_SCORE
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
