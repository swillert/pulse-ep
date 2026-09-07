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
    #: Operator / system markers on the point, by their vendor-defined names
    #: (CARTO: ``Location Only``, ``Scar``, user-defined labels …). A marker,
    #: not a measurement — it says what the operator meant the point for.
    tags: list[str] = field(default_factory=list)
    #: Where this point's beat sits in the signal recorded for it — the
    #: acquisition's own bookkeeping, not a measurement of tissue, which is
    #: why it is not in ``measurements``:
    #:
    #: ``start_time``
    #:     first sample of the recorded window, on the study clock.
    #: ``reference`` / ``map``
    #:     the reference and mapping annotations, as offsets into that window.
    #:     Their *difference* is the activation time (or pace-match score) that
    #:     ``measurements`` carries; these are the components it came from.
    #: ``woi_from`` / ``woi_to``
    #:     the window of interest the annotation was searched in.
    #:
    #: Keys absent from an export are absent here. The names are the ones a
    #: stored :class:`~pulse_ep.core.waveform.Waveform` records for the same
    #: point, so a window and the point it belongs to describe themselves
    #: identically instead of by coincidence.
    annotations: dict = field(default_factory=dict)

    def add(self, name: str, value: float, kind: str, unit: str = "") -> None:
        self.measurements[name] = Measurement(value, kind, unit)

    def get(self, name: str) -> float | None:
        m = self.measurements.get(name)
        return m.value if m is not None else None
