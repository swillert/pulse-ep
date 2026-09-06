"""The two-layer vocabulary: an inventory of quantities + a per-vendor lexicon.

The inventory (``KIND_SPECS``) says what a quantity *is* and what unit it has;
the lexicon says what each acquisition system calls it. These tests pin the
contract between them — above all that a field is named by what it is, so one
name spans both vendors, and that an unrecognised token is still imported.
"""

from __future__ import annotations

from pulse_ep.core.importers.lexicon import (
    CARTO_LEGACY_NAMES,
    ENSITE_DXL_CHANNELS,
    ENSITE_POINT_COLUMNS,
    ENSITE_POLARITY,
    resolve,
)
from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    CFE_MEAN,
    KIND_SPECS,
    UNKNOWN,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
    default_unit,
    field_name,
)


def test_a_field_is_named_by_what_it_is():
    assert field_name(VOLTAGE_BIPOLAR) == "voltage_bipolar"
    assert field_name(ACTIVATION_TIME) == "activation_time"


def test_an_unknown_quantity_keeps_its_vendor_token():
    """Not dropped, not guessed — carried through so it stays reviewable."""
    assert field_name(UNKNOWN, "CFE StdDev v2") == "CFE StdDev v2"
    assert field_name("", "Peak Neg") == "Peak Neg"
    assert field_name(UNKNOWN, None) == "unknown"
    assert field_name(UNKNOWN, "   ") == "unknown"


def test_resolve_is_case_and_whitespace_insensitive():
    assert resolve(ENSITE_DXL_CHANNELS, "CFEmean") == CFE_MEAN
    assert resolve(ENSITE_DXL_CHANNELS, " cfemean ") == CFE_MEAN
    assert resolve(ENSITE_POLARITY, "UNIPOLAR") == VOLTAGE_UNIPOLAR


def test_resolve_never_raises_on_an_unseen_token():
    assert resolve(ENSITE_DXL_CHANNELS, "somethingNew") == UNKNOWN
    assert resolve(ENSITE_DXL_CHANNELS, "") == UNKNOWN
    assert resolve(ENSITE_DXL_CHANNELS, None) == UNKNOWN


def test_every_lexicon_entry_names_a_known_quantity():
    """A lexicon may only point at quantities the inventory defines —
    otherwise a value would carry a kind with no unit and no semantics."""
    for lexicon in (ENSITE_DXL_CHANNELS, ENSITE_POLARITY, ENSITE_POINT_COLUMNS):
        for token, kind in lexicon.items():
            assert kind in KIND_SPECS, f"{token} -> {kind} is not in the inventory"
    for name, kinds in CARTO_LEGACY_NAMES.items():
        for kind in kinds:
            assert kind in KIND_SPECS, f"legacy {name} -> {kind} is not in the inventory"


def test_the_unit_comes_from_the_inventory_not_the_lexicon():
    assert default_unit(resolve(ENSITE_DXL_CHANNELS, "cfemean")) == "ms"
    assert default_unit(resolve(ENSITE_DXL_CHANNELS, "pfreq")) == "Hz"
    assert default_unit(resolve(ENSITE_POLARITY, "bi")) == "mV"
    assert default_unit(UNKNOWN) == ""


def test_both_vendors_name_bipolar_voltage_identically():
    """The whole point: one query spans CARTO and EnSiteX."""
    carto = field_name(VOLTAGE_BIPOLAR)
    ensite = field_name(resolve(ENSITE_POLARITY, "bi"))
    assert carto == ensite == "voltage_bipolar"
