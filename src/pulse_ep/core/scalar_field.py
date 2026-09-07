"""Vendor-neutral per-vertex scalar fields and their physical semantics.

A CARTO or EnSite X mesh carries per-vertex scalar values, but *what* a
value means is decided by the acquisition context, not by a storage slot.
Historically pulse-ep stored the "primary" scalar in ``act_bip[:, 0]`` and
re-derived its meaning heuristically wherever it was read (activation time
vs. pace-mapping score). :class:`ScalarField` makes that meaning explicit:
the **importer declares the ``kind``**, conditioning is applied once at
import, and downstream analysis stays semantics-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# --- controlled vocabulary of physical quantities -------------------------

ACTIVATION_TIME = "activation_time"
PACEMAP_SCORE = "pacemap_score"
VOLTAGE_BIPOLAR = "voltage_bipolar"
VOLTAGE_UNIPOLAR = "voltage_unipolar"
#: bipolar amplitude measured between neighbouring *micro*-electrodes (CARTO
#: "µBi" on OCTARAY / QDOT catheters) — a different quantity from the
#: electrode-pair bipolar voltage, and recorded alongside it.
VOLTAGE_BIPOLAR_MICRO = "voltage_bipolar_micro"
# per-point measurement quantities (shared vocabulary with per-vertex fields)
CONTACT_FORCE = "contact_force"
CORRELATION = "correlation"
SNR = "snr"
IMPEDANCE = "impedance"
#: the annotation offset a map was measured with — a window setting, not a
#: per-point activation (it is frequently constant across a whole export).
ANNOTATION_TIME = "annotation_time"
VOLTAGE_PEAK_NEGATIVE = "voltage_peak_negative"
#: complex fractionated electrogram descriptors (EnSite "CFE", CARTO "CFAE")
CFE_MEAN = "cfe_mean"
CFE_STDDEV = "cfe_stddev"
FRACTIONATION = "fractionation"
PEAK_FREQUENCY = "peak_frequency"
#: the mapping system's own acceptance score for an acquired point
MAP_SCORE = "map_score"
#: a quantity the vendor lexicon does not (yet) recognise. It is imported
#: anyway, under its raw vendor token — see :func:`field_name`.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class KindSpec:
    """Fixed, vendor-neutral semantics of a scalar ``kind``.

    Only intrinsic properties of the quantity live here — its unit and
    whether it is a relative-comparison measure. Vendor-specific *decoding*
    (sign conventions, export sentinels, detecting which kind a slot holds)
    belongs in that vendor's importer, not here.
    """

    unit: str
    #: a relative-comparison quantity (e.g. pace-map similarity to a
    #: template) — comparing two such maps differs from a voltage delta.
    relative_comparison: bool = False


KIND_SPECS: dict[str, KindSpec] = {
    ACTIVATION_TIME: KindSpec(unit="ms"),
    PACEMAP_SCORE: KindSpec(unit="%", relative_comparison=True),
    VOLTAGE_BIPOLAR: KindSpec(unit="mV"),
    VOLTAGE_UNIPOLAR: KindSpec(unit="mV"),
    VOLTAGE_BIPOLAR_MICRO: KindSpec(unit="mV"),
    CONTACT_FORCE: KindSpec(unit="g"),
    CORRELATION: KindSpec(unit="", relative_comparison=True),
    SNR: KindSpec(unit=""),
    IMPEDANCE: KindSpec(unit="ohm"),
    ANNOTATION_TIME: KindSpec(unit="ms"),
    VOLTAGE_PEAK_NEGATIVE: KindSpec(unit="mV"),
    CFE_MEAN: KindSpec(unit="ms"),
    CFE_STDDEV: KindSpec(unit="ms"),
    FRACTIONATION: KindSpec(unit=""),  # a count of deflections
    PEAK_FREQUENCY: KindSpec(unit="Hz"),
    MAP_SCORE: KindSpec(unit=""),
}


def default_unit(kind: str) -> str:
    spec = KIND_SPECS.get(kind)
    return spec.unit if spec is not None else ""


def field_name(kind: str, vendor_token: str | None = None) -> str:
    """The canonical name a quantity is registered under.

    **A field is named by what it is.** Asking for a name and asking for a
    kind then become the same question, so CARTO's bipolar voltage answers to
    the same name as EnSite X's and one query spans both vendors. (Historically
    they did not: CARTO wrote ``act``/``vol`` while EnSite X wrote
    ``voltage_bipolar`` — the same quantity under two names, findable by
    neither.)

    A quantity the vendor lexicon does not recognise keeps its raw vendor
    token instead, so it is still imported and still visible for review — a
    closed vocabulary that silently drops the unfamiliar is how whole channels
    go missing.
    """
    if kind and kind != UNKNOWN:
        return kind
    return (vendor_token or "").strip() or UNKNOWN


@dataclass
class ScalarField:
    """A named per-vertex scalar with declared physical meaning.

    Values are stored as-is; conditioning (vendor decode) is the importer's
    responsibility and happens before registration.

    :param values: per-vertex values (1-D), already conditioned.
    :param kind: one of the controlled ``*_TIME`` / ``*_SCORE`` / ``VOLTAGE_*``
        constants — declared by the importer.
    :param unit: physical unit; defaults from the kind.
    :param status_mask: optional per-vertex validity (``True`` = valid).
    :param source: provenance tag (vendor / export version).
    """

    values: np.ndarray
    kind: str
    unit: str = ""
    status_mask: np.ndarray | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values)
        if not self.unit:
            self.unit = default_unit(self.kind)

    @property
    def relative_comparison(self) -> bool:
        spec = KIND_SPECS.get(self.kind)
        return bool(spec.relative_comparison) if spec is not None else False

    def to_dict(self) -> dict:
        """JSON-serialisable form (for the ``scalar_fields`` JSONB column)."""
        mask = self.status_mask
        return {
            "values": np.asarray(self.values).tolist(),
            "kind": self.kind,
            "unit": self.unit,
            "status_mask": None if mask is None else np.asarray(mask).tolist(),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScalarField:
        mask = d.get("status_mask")
        return cls(
            values=np.asarray(d["values"]),
            kind=d["kind"],
            unit=d.get("unit", ""),
            status_mask=None if mask is None else np.asarray(mask),
            source=d.get("source"),
        )
