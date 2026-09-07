"""EnSite X ``Electrode_Locations.csv`` — catheter geometry over time.

Structure taken from a real 6.0.0 export: preamble, a status-bit legend, the
``channel,catheter name,electrode name,is visible`` table, a column glossary,
and only then the ``t_dws`` sample matrix. In that export the electrode table
sits well above the samples, which is why the reader looks for the marker and
never for "the first table". Values here are generated.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.importers.ensite import (
    _reader_for,
    parse_channel_map,
    parse_ensite_electrode_locations,
    position_channel_unit,
)
from pulse_ep.core.waveform import UNKNOWN_UNIT

_EXPORT = """Export File Version: 5.4
Export Data Element: Electrode_Locations
Exported from Software Version: 6.0.0.683129
Export from Study: 70538697-25b4-43bd-854c-a9000da6fa96
Export from Segment: Segment A
Positional Reference Type: system

Location Data Status Bits
------------------------------------
Name: Bit
------------------------------------
IMPEDANCE_DATA_INVALID: 14
UNCOMPUTED: 15

channel,catheter name,electrode name,is visible
0,CS,D,1
1,CS,2,1
2,HDG,A1,0

t_dws: timepoint as seen in DWS in HH:MM:SS.mSmSmS format
t_ref: timepoint relative to first timepoint in seconds
reliability : 0-unreliable, 1-reliable
c###x|y|z : channel ### x|y|z coordinate
Number of waves (columns): 20
Number of samples (rows): 2

t_dws,t_secs,t_usecs,t_ref,reliability,c0x,c0y,c0z,c0_ds,c0_ps,c1x,c1y,c1z,c1_ds,c1_ps
 14:43:09.815,1782225789,814522,0,1,48.162,-117.186,358.992,32,36864,48.029,-115.577,357.468,32,36864
 14:43:09.825,1782225789,824522,0.01,1,48.423,-114.066,355.459,32,36864,49.215,-112.434,353.202,32,36864
"""


def test_coordinates_are_millimetres_and_status_columns_are_not():
    w = parse_ensite_electrode_locations(_EXPORT, name="Electrode_Locations.csv")
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["c0x"] == got["c0y"] == got["c0z"] == "mm"
    assert got["c1z"] == "mm"
    assert got["c0_ds"] == got["c0_ps"] == UNKNOWN_UNIT
    assert got["reliability"] == UNKNOWN_UNIT


def test_the_raw_column_names_are_kept():
    """So that what is stored still matches what the export says.

    The electrode labels are reachable through ``meta["channels"]`` instead of
    replacing the names, which would make the two impossible to compare.
    """
    w = parse_ensite_electrode_locations(_EXPORT)
    assert "c0x" in w.channels
    assert not any("CS" in c for c in w.channels)
    assert w.meta["channels"]["0"]["catheter"] == "CS"


def test_the_channel_table_is_the_bridge_to_electrode_labels():
    m = parse_channel_map(_EXPORT)
    assert m == {
        "0": {"catheter": "CS", "electrode": "D", "visible": True},
        "1": {"catheter": "CS", "electrode": "2", "visible": True},
        "2": {"catheter": "HDG", "electrode": "A1", "visible": False},
    }


def test_samples_rate_and_type():
    w = parse_ensite_electrode_locations(_EXPORT, name="Electrode_Locations.csv")
    assert w.signal_type == "electrode_position"
    assert w.data.shape == (2, 11)  # 15 columns minus the four t_* ones
    assert w.sample_rate == 100.0
    np.testing.assert_allclose(w.data[:, w.channels.index("c0x")], [48.162, 48.423])


def test_the_sample_header_is_found_below_the_other_tables():
    """The channel table and the glossary both precede it in a real export."""
    w = parse_ensite_electrode_locations(_EXPORT)
    # Neither the legend nor the channel table leaked into the channels.
    assert "IMPEDANCE_DATA_INVALID" not in w.channels
    assert "channel" not in w.channels
    assert w.meta["export_data_element"] == "Electrode_Locations"


def test_a_file_without_a_channel_table_still_parses():
    stripped = "\n".join(
        ln for ln in _EXPORT.splitlines() if not ln.startswith(("channel,", "0,", "1,", "2,"))
    )
    w = parse_ensite_electrode_locations(stripped)
    assert w.meta["channels"] == {}
    assert w.data.shape[1] == 11


@pytest.mark.parametrize(
    "column, unit",
    [
        ("c0x", "mm"),
        ("c199z", "mm"),
        ("C7Y", "mm"),
        ("c0_ds", UNKNOWN_UNIT),
        ("t_ref", UNKNOWN_UNIT),
    ],
)
def test_position_unit_lookup(column, unit):
    assert position_channel_unit(column) == unit


def test_the_ingest_iterator_picks_the_right_parser():
    assert _reader_for("x/Electrode_Locations.csv") is parse_ensite_electrode_locations
