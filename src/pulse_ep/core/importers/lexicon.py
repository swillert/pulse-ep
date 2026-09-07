"""What each acquisition system calls a quantity.

Two halves make up the vocabulary, and keeping them apart is the point:

- **The inventory** — what a value *is*, and its unit — is
  :data:`~pulse_ep.core.scalar_field.KIND_SPECS`. Closed and curated: a
  quantity is added there deliberately, once, for every vendor.
- **The lexicon** — this module — is the other half: the token each system
  exports that quantity under. Open-ended, one table per vendor, and pure
  data. It is the only place a vendor's spelling appears.

Before this split the mapping lived in six ad-hoc places across two importers
(a polarity dict, a channel dict, a column tuple, a descriptor function, and
CARTO's two hardcoded names), so there was no obvious home for a new one and
every export shape grew its own.

The lexicon is deliberately *code*, not a database table: a wrong entry
mislabels a clinical measurement silently, so it must be reviewed, tested and
versioned alongside the parser that uses it. What belongs in the database is
the presentation layer — label, colormap and default range per kind.

Value-based decoding (CARTO's sign convention for its overloaded primary
slot, EnSite's export sentinels) is *not* lexicon: it inspects data rather
than names and stays in the vendor importer.
"""

from __future__ import annotations

from collections.abc import Mapping

from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    CFE_MEAN,
    CFE_STDDEV,
    CONTACT_FORCE,
    CORRELATION,
    FRACTIONATION,
    IMPEDANCE,
    MAP_SCORE,
    PACEMAP_SCORE,
    PEAK_FREQUENCY,
    SNR,
    UNKNOWN,
    VOLTAGE_BIPOLAR,
    VOLTAGE_BIPOLAR_MICRO,
    VOLTAGE_PEAK_NEGATIVE,
    VOLTAGE_UNIPOLAR,
)

#: EnSiteX DxL ``Map type:`` channel token -> quantity. ``pp`` is absent
#: because its kind depends on the polarity suffix (see :data:`ENSITE_POLARITY`).
ENSITE_DXL_CHANNELS: Mapping[str, str] = {
    "lat": ACTIVATION_TIME,
    "score": MAP_SCORE,
    "cfemean": CFE_MEAN,
    "cfestddev": CFE_STDDEV,
    "fractionation": FRACTIONATION,
    "pfreq": PEAK_FREQUENCY,
    "pneg": VOLTAGE_PEAK_NEGATIVE,
}

#: The DxL channels whose quantity is decided by the polarity suffix rather
#: than the channel token. Explicit, so that an *unknown* channel is reported
#: as unknown instead of quietly inheriting the voltage reading.
ENSITE_POLARITY_CHANNELS: frozenset[str] = frozenset({"pp"})

#: EnSiteX polarity suffix -> the voltage quantity it denotes. ``omni`` is the
#: omnipolar P-P amplitude, recorded as bipolar.
ENSITE_POLARITY: Mapping[str, str] = {
    "bi": VOLTAGE_BIPOLAR,
    "bipolar": VOLTAGE_BIPOLAR,
    "omni": VOLTAGE_BIPOLAR,
    "uni": VOLTAGE_UNIPOLAR,
    "unipolar": VOLTAGE_UNIPOLAR,
}

#: Columns of the raw-archive-derived ``map_*_points.csv`` -> quantity.
ENSITE_POINT_COLUMNS: Mapping[str, str] = {
    "pp": VOLTAGE_BIPOLAR,
    "unipolemaxpp": VOLTAGE_UNIPOLAR,
    "correctedlat": ACTIVATION_TIME,
    "correlationcoefficient": CORRELATION,
    "snr": SNR,
    "force": CONTACT_FORCE,
}

#: CARTO's legacy field names -> the quantities they held. Kept so studies
#: imported before fields were named by kind, and clients that still ask for
#: ``act``/``vol``, keep resolving. ``act`` is genuinely ambiguous — the slot
#: holds either quantity — so it lists both and the caller picks whichever the
#: map actually carries (see ``EPMap.get_scalar``).
CARTO_LEGACY_NAMES: Mapping[str, tuple[str, ...]] = {
    "act": (ACTIVATION_TIME, "pacemap_score"),
    "vol": (VOLTAGE_BIPOLAR,),
}

#: CARTO ``.mesh`` ``[VerticesColorsSection]`` column name -> quantity.
#:
#: The file names its own columns; before this table they were read by
#: position, which silently dropped ``Paso`` (the PASO pace-match score) and
#: ``µBi``, and would have mislabelled every column of an export that ordered
#: them differently.
#:
#: Columns deliberately absent: ``A1`` / ``A2`` / ``A2-A1`` / ``SCI`` / ``ICL``
#: / ``ACL``. They are real CARTO quantities but their exact semantics are not
#: established here, and a guessed kind mislabels a clinical measurement
#: silently — they import under their raw vendor token instead (see
#: :func:`~pulse_ep.core.scalar_field.field_name`).
#:
#: ``µ`` is the MICRO SIGN in the export but casefolds to GREEK SMALL LETTER
#: MU, so both spellings are keys — :func:`resolve` casefolds before lookup.
CARTO_MESH_COLORS: Mapping[str, str] = {
    "unipolar": VOLTAGE_UNIPOLAR,
    "bipolar": VOLTAGE_BIPOLAR,
    "lat": ACTIVATION_TIME,
    "impedance": IMPEDANCE,
    "force": CONTACT_FORCE,
    "paso": PACEMAP_SCORE,
    "μbi": VOLTAGE_BIPOLAR_MICRO,  # µBi, casefolded
    "µbi": VOLTAGE_BIPOLAR_MICRO,  # µBi, as written
    "ubi": VOLTAGE_BIPOLAR_MICRO,
}


def resolve(lexicon: Mapping[str, str], token: str) -> str:
    """The quantity a vendor token denotes, or :data:`UNKNOWN`.

    Never raises: an export carrying something the lexicon has not seen must
    still import (under its raw token) rather than abort or lose the channel.
    """
    return lexicon.get((token or "").strip().casefold(), UNKNOWN)
