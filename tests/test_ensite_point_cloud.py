"""EnSite X ``Model_Point_Cloud.csv`` — every position collected while the
anatomical model was being built.

It is the one export in the per-timepoint family with its own header
(``Time,``), a single wall-clock time column, a text column, and a span of the
whole study rather than one segment. Structure from a real 6.0.0 export;
values generated.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.importers.ensite import (
    POINT_CLOUD_RESPIRATION_CODES,
    _reader_for,
    parse_ensite_point_cloud,
    parse_ensite_timeseries,
)
from pulse_ep.core.waveform import UNKNOWN_UNIT

_CLOUD = """Export File Version: 5.16
Export Data Element: Model_Point_Cloud
Exported from Software Version: 6.0.0.683129
Export from Study: 70538697-25b4-43bd-854c-a9000da6fa96
Export from Segment: N/A
Export Start Time (h:m:s.msec): N/A
Field Scaling: off
DIF Fusion: on
Number of waves (columns): 8
Number of samples (rows): 4

Time,raw_x,raw_y,raw_z,trn_x,trn_y,trn_z,respiration_phase
11:52:57.695,130.415,-54.239,104.847,140.415,-154.239,404.847,EXPIRATION
11:52:57.775,129.471,-55.151,109.600,139.471,-155.151,409.600,EXPIRATION
11:52:58.695,132.146,-53.818,105.380,142.146,-153.818,405.380,INSPIRATION
11:53:57.695,134.565,-52.461,100.636,144.565,-152.461,400.636,UNKNOWN
EOF
"""


def test_the_two_frames_are_not_given_the_same_unit():
    """``trn_*`` shares the mesh's frame; ``raw_*`` is the tracking space.

    On the reference export the transformed points sit a median 8.5 mm from
    the nearest mesh vertex and the raw ones some 360 mm away — a different
    frame, whose scaling the preamble does not state (``Field Scaling: off``).
    Calling both millimetres because the numbers look alike is exactly the
    guess the unit field exists to prevent.
    """
    w = parse_ensite_point_cloud(_CLOUD)
    got = dict(zip(w.channels, w.units, strict=True))
    assert got["trn_x"] == got["trn_y"] == got["trn_z"] == "mm"
    assert got["raw_x"] == got["raw_y"] == got["raw_z"] == UNKNOWN_UNIT


def test_the_text_column_is_encoded_rather_than_dropped():
    """Which phase a point was collected in is what makes two positions of the
    same wall differ — so it cannot simply be discarded to fit a float array."""
    w = parse_ensite_point_cloud(_CLOUD)
    phase = w.data[:, w.channels.index("respiration_phase")]
    np.testing.assert_array_equal(phase, [1.0, 1.0, 2.0, 0.0])
    assert w.meta["respiration_phase_codes"] == POINT_CLOUD_RESPIRATION_CODES


def test_an_unseen_phase_becomes_nan_rather_than_a_wrong_code():
    text = _CLOUD.replace("INSPIRATION", "SOMETHING_ELSE", 1)
    w = parse_ensite_point_cloud(text)
    phase = w.data[:, w.channels.index("respiration_phase")]
    assert np.isnan(phase[2])
    assert not np.isnan(phase[[0, 1, 3]]).any()


def test_the_wall_clock_becomes_seconds_from_the_first_sample():
    """The rest of the family carries t_ref, "relative to first timepoint in
    seconds"; converting here gives every stored window one time axis."""
    w = parse_ensite_point_cloud(_CLOUD)
    np.testing.assert_allclose(w.time, [0.0, 0.08, 1.0, 60.0], atol=1e-6)


def test_no_fixed_sample_rate_is_claimed():
    """The samples arrive in bursts — a multi-electrode catheter contributes
    several per frame — so a rate derived from their spacing would be fiction."""
    assert parse_ensite_point_cloud(_CLOUD).sample_rate is None


def test_the_eof_marker_is_not_a_point():
    w = parse_ensite_point_cloud(_CLOUD)
    assert w.data.shape == (4, 7)
    assert not np.isnan(w.data[:, w.channels.index("trn_x")]).any()


def test_it_is_recognisable_as_whole_study_rather_than_a_segment():
    w = parse_ensite_point_cloud(_CLOUD)
    assert w.signal_type == "model_point_cloud"
    assert w.meta["segment"] == "N/A"
    assert w.meta["field_scaling"] == "off" and w.meta["dif_fusion"] == "on"


def test_its_own_reader_is_chosen():
    """It shares the family's preamble but not its ``t_dws`` header."""
    assert _reader_for("x/Model_Point_Cloud.csv") is parse_ensite_point_cloud
    assert _reader_for("x/Electrode_Locations.csv") is parse_ensite_timeseries


def test_a_file_without_the_point_header_says_which_marker_was_missing():
    with pytest.raises(ValueError, match="Time,"):
        parse_ensite_point_cloud("Export Data Element: Model_Point_Cloud\n")
