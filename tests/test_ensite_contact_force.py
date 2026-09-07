"""EnSite X contact-force exports (Raw / Filtered / Computed).

Structure taken from a real 6.0.0 export: a metadata preamble, a
data-status-bit legend, then a ``t_dws,`` header and the sample matrix. The
values here are generated — the real export is patient data.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.importers.ensite import (
    force_channel_unit,
    parse_dws_table,
    parse_ensite_contact_force,
)
from pulse_ep.core.waveform import UNKNOWN_UNIT

_PREAMBLE = """Export File Version: 5.2
Export Data Element: {element}
Exported from Software Version: 6.0.0.683129
Export from Study: 70538697-25b4-43bd-854c-a9000da6fa96
Export from Segment: Segment A
Export User Comments: Add comments here
Export Duration (h:m:s.msec): 00:00:00.150
EnGuide Responsiveness filter: Moderate

Data status bits
-------------------------------------------
Name : Bit
-------------------------------------------
CATHETER_NOT_CONNECTED_OR_NOT_ACCEPTED : 0
MANUAL_FORCE_RESET_PERFORMED : 1
ABLATION_IN_PROGRESS : 2
"""

_ONE_SENSOR = (
    "t_dws,t_secs,t_usecs,t_ref,reliability,totalForce,forceTimeIntegral,alphaAngle,"
    "thetaAngle,cavityDistance1,thermocouple1Temp,ablationCurrent,qStatus\n"
    " 14:43:09.815,1782225789,814522,0,1,12.5,427,60,267,3.2,37.1,0,0\n"
    " 14:43:09.835,1782225789,834522,0.02,1,13.0,431,61,268,3.1,37.2,0,0\n"
    " 14:43:09.855,1782225789,854522,0.04,1,13.4,436,62,269,3.0,37.2,0,0\n"
)

_TWO_SENSORS = (
    "t_dws,t_secs,t_usecs,t_ref,reliability,totalForce_0,alphaAngle_0,cavityDistance1_0,"
    "totalForce_1,alphaAngle_1,cavityDistance1_1\n"
    " 14:43:09.815,1782225789,814522,0,1,12.5,60,3.2,8.1,44,5.0\n"
    " 14:43:09.835,1782225789,834522,0.02,1,13.0,61,3.1,8.4,45,4.9\n"
)


def _export(element: str, body: str) -> str:
    return _PREAMBLE.format(element=element) + body


def test_the_three_stages_are_told_apart():
    """A listing of three windows all called "contact_force" would be useless."""
    for stage in ("Raw", "Filtered", "Computed"):
        w = parse_ensite_contact_force(
            _export(f"Contact_Force_{stage}", _ONE_SENSOR), name=f"Contact_Force_{stage}.csv"
        )
        assert w.signal_type == f"contact_force_{stage.lower()}"


def test_samples_channels_and_rate():
    w = parse_ensite_contact_force(_export("Contact_Force_Raw", _ONE_SENSOR))
    assert w.data.shape == (3, 9)  # 13 columns minus the four t_* ones
    assert "t_ref" not in w.channels and "t_secs" not in w.channels
    assert w.channels[0] == "reliability"  # a flag, but not a time column
    assert w.sample_rate == 50.0
    np.testing.assert_allclose(w.data[:, w.channels.index("totalForce")], [12.5, 13.0, 13.4])


def test_one_file_carries_four_different_units():
    """Which is the whole reason units are per channel and not per waveform."""
    w = parse_ensite_contact_force(_export("Contact_Force_Raw", _ONE_SENSOR))
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["totalForce"] == "g"
    assert got["alphaAngle"] == "deg"
    assert got["cavityDistance1"] == "mm"
    assert got["thermocouple1Temp"] == "degC"
    assert len(set(w.units)) >= 4


def test_a_column_the_lexicon_does_not_know_is_unknown_not_plausible():
    """An ammeter reading in A and one in mA look identical in a CSV."""
    w = parse_ensite_contact_force(_export("Contact_Force_Raw", _ONE_SENSOR))
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["ablationCurrent"] == UNKNOWN_UNIT
    assert got["qStatus"] == UNKNOWN_UNIT
    assert got["reliability"] == UNKNOWN_UNIT


def test_the_per_sensor_suffix_resolves_to_the_same_unit():
    """Computed indexes per sensor; Raw and Filtered carry one and no suffix."""
    w = parse_ensite_contact_force(_export("Contact_Force_Computed", _TWO_SENSORS))
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["totalForce_0"] == got["totalForce_1"] == "g"
    assert got["cavityDistance1_0"] == got["cavityDistance1_1"] == "mm"


@pytest.mark.parametrize(
    "column, unit",
    [("totalForce", "g"), ("totalForce_11", "g"), ("THETAANGLE", "deg"), ("nope_0", UNKNOWN_UNIT)],
)
def test_unit_lookup_ignores_case_and_sensor_index(column, unit):
    assert force_channel_unit(column) == unit


def test_the_header_is_found_by_its_marker_not_by_position():
    """The legend block above it varies in length between exports and files."""
    meta, df = parse_dws_table(_export("Contact_Force_Raw", _ONE_SENSOR))
    assert meta["Export Data Element"] == "Contact_Force_Raw"
    assert meta["Export from Segment"] == "Segment A"
    assert "totalForce" in df.columns
    # The legend's "NAME : 0" lines must not be mistaken for metadata columns.
    assert "CATHETER_NOT_CONNECTED_OR_NOT_ACCEPTED" in meta


def test_a_file_without_a_sample_matrix_says_so():
    with pytest.raises(ValueError, match="t_dws"):
        parse_ensite_contact_force(_PREAMBLE.format(element="Contact_Force_Raw"))
