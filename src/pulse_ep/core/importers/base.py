"""Vendor importer protocol + a small registry for auto-detection.

A ``VendorImporter`` turns an :class:`ImportSource` into vendor-neutral
:class:`~pulse_ep.core.study.Study` objects. ``sniff`` lets one command
auto-detect the vendor (CARTO vs EnSite X) without the caller knowing it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pulse_ep.core.importers.plan import ImportPlan
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.study import Study


@runtime_checkable
class VendorImporter(Protocol):
    """The minimum an importer must provide: recognise a source, and decode it.

    ``prepare(source) -> ImportPlan`` and ``commit(plan, source)`` are an
    *optional* refinement on top, for vendors whose exports are worth reviewing
    before they are written. Importers without them still work everywhere —
    see :func:`prepare_plan` / :func:`commit_plan`, which every caller should
    use instead of reaching for the methods directly.
    """

    name: str

    def sniff(self, source: ImportSource) -> bool:
        """Return True if this importer recognises the source's layout."""
        ...

    def parse(self, source: ImportSource) -> list[Study]:
        """Decode the source into vendor-neutral Study objects."""
        ...


def prepare_plan(importer: VendorImporter, source: ImportSource) -> ImportPlan:
    """The importer's reviewable plan, or an empty one for vendors without.

    A vendor that only implements ``parse`` cannot describe its export without
    doing the full (expensive) decode, so it proposes nothing and the plan
    carries an issue saying so — the import still runs, just unreviewed.
    """
    prepare = getattr(importer, "prepare", None)
    if prepare is not None:
        return prepare(source)
    return ImportPlan(
        issues=[
            f"{importer.name}: no reviewable plan for this vendor — "
            "committing imports everything the export contains"
        ]
    )


def commit_plan(importer: VendorImporter, plan: ImportPlan, source: ImportSource) -> list[Study]:
    """Execute a (reviewer-edited) plan, falling back to a straight parse."""
    commit = getattr(importer, "commit", None)
    if commit is not None:
        return commit(plan, source)
    return importer.parse(source)


_REGISTRY: list[VendorImporter] = []


def register_importer(importer: VendorImporter) -> VendorImporter:
    _REGISTRY.append(importer)
    return importer


def get_importers() -> list[VendorImporter]:
    return list(_REGISTRY)


def get_importer(name: str) -> VendorImporter | None:
    """Return the registered importer with this ``name`` (e.g. "ensite")."""
    return next((imp for imp in _REGISTRY if imp.name == name), None)


def waveform_iterator(vendor: str | None):
    """The ``iter_waveforms(study_plan, source)`` of a vendor's importer.

    Signal files are the one part of an export with no vendor-neutral shape at
    all — EnSite X writes a handful of long multi-channel CSVs, CARTO one short
    fixed-window file per acquired point — so the ingest path dispatches here
    rather than hard-coding one vendor's parser as the meaning of "waveform".

    :raises ValueError: for a vendor with no signal importer, rather than
        silently importing nothing.
    """
    from pulse_ep.core.importers import carto_signal, ensite

    iterators = {
        "carto": carto_signal.iter_waveforms,
        "ensite": ensite.iter_waveforms,
        "ensitex": ensite.iter_waveforms,
    }
    iterator = iterators.get((vendor or "").strip().casefold())
    if iterator is None:
        raise ValueError(f"no waveform importer for vendor {vendor!r}")
    return iterator


def detect_vendor(source: ImportSource) -> VendorImporter | None:
    """First registered importer whose ``sniff`` matches, else ``None``."""
    for importer in _REGISTRY:
        try:
            if importer.sniff(source):
                return importer
        except Exception:  # a sniff must never crash detection
            continue
    return None
