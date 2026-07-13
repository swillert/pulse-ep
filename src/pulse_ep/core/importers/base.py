"""Vendor importer protocol + a small registry for auto-detection.

A ``VendorImporter`` turns an :class:`ImportSource` into vendor-neutral
:class:`~pulse_ep.core.study.Study` objects. ``sniff`` lets one command
auto-detect the vendor (CARTO vs EnSiteX) without the caller knowing it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.study import Study


@runtime_checkable
class VendorImporter(Protocol):
    name: str

    def sniff(self, source: ImportSource) -> bool:
        """Return True if this importer recognises the source's layout."""
        ...

    def parse(self, source: ImportSource) -> list[Study]:
        """Decode the source into vendor-neutral Study objects."""
        ...


_REGISTRY: list[VendorImporter] = []


def register_importer(importer: VendorImporter) -> VendorImporter:
    _REGISTRY.append(importer)
    return importer


def get_importers() -> list[VendorImporter]:
    return list(_REGISTRY)


def get_importer(name: str) -> VendorImporter | None:
    """Return the registered importer with this ``name`` (e.g. "ensite")."""
    return next((imp for imp in _REGISTRY if imp.name == name), None)


def detect_vendor(source: ImportSource) -> VendorImporter | None:
    """First registered importer whose ``sniff`` matches, else ``None``."""
    for importer in _REGISTRY:
        try:
            if importer.sniff(source):
                return importer
        except Exception:  # a sniff must never crash detection
            continue
    return None
