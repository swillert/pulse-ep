"""Per-point measurements — the vendor-neutral acquisition sample.

A measurement point is where a signal was acquired; it carries an OPEN set of
named quantities (``measurements``) rather than fixed vendor columns, reusing
the same ``kind`` vocabulary as per-vertex :class:`ScalarField`. Electrode
geometry is likewise an open map keyed by connector/channel, not fixed CARTO
catheter columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pulse_ep.core.scalar_field import default_unit


@dataclass
class Measurement:
    """One named per-point quantity (e.g. ``voltage_bipolar`` = 1.2 mV)."""

    value: float
    kind: str
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.unit:
            self.unit = default_unit(self.kind)


@dataclass
class MeasurementPoint:
    """A single acquisition point on / near the chamber surface."""

    position: np.ndarray  # (3,)
    measurements: dict[str, Measurement] = field(default_factory=dict)
    electrodes: dict[str, np.ndarray] = field(default_factory=dict)  # label -> (3,)
    source_id: str | None = None  # vendor point id
    index: int | None = None  # order within the map

    def add(self, name: str, value: float, kind: str, unit: str = "") -> None:
        self.measurements[name] = Measurement(value, kind, unit)

    def get(self, name: str) -> float | None:
        m = self.measurements.get(name)
        return m.value if m is not None else None
