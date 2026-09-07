"""The remaining EnSite X per-timepoint exports: contact index and magnetic location.

They share the ``t_dws`` shape with contact force and electrode locations, so
one reader serves all of them; what differs is which quantities the columns
hold. Structure taken from a real 6.0.0 export, values generated.
"""

from __future__ import annotations

import pytest

from pulse_ep.core.importers.ensite import (
    _reader_for,
    parse_ensite_timeseries,
    parse_ensite_waveforms,
    timeseries_channel_unit,
)
from pulse_ep.core.waveform import UNKNOWN_UNIT

_HEAD = """Export File Version: {version}
Export Data Element: {element}
Exported from Software Version: 6.0.0.683129
Export from Study: 70538697-25b4-43bd-854c-a9000da6fa96
Export from Segment: Segment A
"""

_CONTACT_INDEX = (
    _HEAD.format(version="1.0", element="Contact_Index_Data_Computed")
    + """
Contact Level
------------------------------------
No_CI_enabled_catheter_connected: -1
SUBOPTIMAL: 1
OPTIMAL: 2

channel,catheter name,electrode name,is visible
0,HDG,A1,1

t_dws,t_secs,t_usecs,t_ref,c0_cos,c0_cos_ds,c0_cos_ps,c0_beciMag,c0_beciMag_ds,c0_beciMag_ps,c0_contactIndex,c0_contactIndex_ds,c0_contactIndex_ps,c0_contactLevel,c0_contactLevel_ds,c0_contactLevel_ps
 14:43:09.815,1782225789,814522,0,0.51,0,0,120.5,0,0,42,0,0,2,0,0
 14:43:09.835,1782225789,834522,0.02,0.53,0,0,121.0,0,0,44,0,0,2,0,0
"""
)

_MAGNETIC = (
    _HEAD.format(version="1.1", element="Respiration_Compensated_Magnetic_Location")
    + """
Magnetic Data Status Bits (dataStatusBits)
----------------------------------------
MAG_MDS_OUT_OF_MOTION_BOX: 1

channel 51: Magnetic1
channel 72: MDS

t_dws,t_secs,t_usecs,t_ref,reliability,handle_0,status_0,qx_0,qy_0,qz_0,q0_0,tx_0,ty_0,tz_0,quality_0,AngleFromMidline_0,dataStatusBits_0
 14:43:09.815,1782225789,814522,0,1,10,0,0.98778,-0.155659,0.00019,-0.00783,3.79541,119.601,12.5958,0.0824,15,0
 14:43:09.825,1782225789,824522,0.01,1,10,0,0.98801,-0.155001,0.00021,-0.00780,3.80112,119.640,12.6001,0.0825,15,0
"""
)


def test_contact_index_has_no_physical_units_at_all():
    """Every column is a trigonometric component, an index or a status code.

    Nothing here is measured in anything, so ``unknown`` throughout is the
    honest answer rather than a gap somebody forgot to fill.
    """
    w = parse_ensite_timeseries(_CONTACT_INDEX)
    assert w.signal_type == "contact_index_data_computed"
    assert set(w.units) == {UNKNOWN_UNIT}
    assert "c0_contactIndex" in w.channels
    assert w.data.shape == (2, 12)


def test_magnetic_location_separates_translation_from_rotation():
    """The quaternion has no unit; the translation is in the mesh's frame."""
    w = parse_ensite_timeseries(_MAGNETIC)
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["tx_0"] == got["ty_0"] == got["tz_0"] == "mm"
    assert got["AngleFromMidline_0"] == "deg"
    assert got["qx_0"] == got["q0_0"] == UNKNOWN_UNIT
    assert got["handle_0"] == got["status_0"] == UNKNOWN_UNIT


def test_the_four_magnetic_variants_stay_apart():
    """They are the same quantity computed four ways, not one window."""
    seen = set()
    for element in (
        "Raw_Magnetic_Location",
        "Filtered_Magnetic_Location",
        "Computed_Magnetic_Location",
        "Respiration_Compensated_Magnetic_Location",
    ):
        text = _MAGNETIC.replace("Respiration_Compensated_Magnetic_Location", element, 1)
        seen.add(parse_ensite_timeseries(text).signal_type)
    assert len(seen) == 4
    assert "raw_magnetic_location" in seen


def test_electrograms_keep_the_names_they_are_stored_under():
    """Renaming them would orphan every waveform already in a database."""
    from tests.test_ensite_waveforms import _WF

    assert parse_ensite_waveforms(
        _WF, name="EP_Catheter_Bipolar_Waveforms_Filtered"
    ).signal_type == ("egm_bipolar")


@pytest.mark.parametrize(
    "column, unit",
    [
        ("c0_contactIndex", UNKNOWN_UNIT),
        ("c0_contactIndex_ds", UNKNOWN_UNIT),  # a bitfield, not an index
        ("totalForce_0", "g"),
        ("totalForce_0_ds", UNKNOWN_UNIT),  # a status column never inherits
        ("tx_11", "mm"),
        ("c3z", "mm"),
    ],
)
def test_status_columns_never_inherit_their_quantitys_unit(column, unit):
    assert timeseries_channel_unit(column) == unit


def test_every_family_reaches_the_one_reader():
    for name in (
        "x/Contact_Force_Raw.csv",
        "x/Electrode_Locations.csv",
        "x/Contact_Index_Data_Computed.csv",
        "x/Raw_Magnetic_Location.csv",
    ):
        assert _reader_for(name) is parse_ensite_timeseries
    assert _reader_for("x/EP_Catheter_Bipolar_Waveforms.csv") is parse_ensite_waveforms
