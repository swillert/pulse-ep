"""EnSite waveform CSV parser (preamble + t_dws header + triplet channels)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_waveforms

_WF = """Export File Version: 5.2
Export Data Element: EP_Catheter_Bipolar_Waveforms_Filtered
Exported from Software Version: 3.0.1
Export from Study: b180
Export from Segment: Stim LA
Highpass: 30 Hz
Lowpass: 300 Hz
Notch: NT_ON
Number of Catheters: 1
Catheter[0](name, num electrodes): RV,2
   Electrode[0](name, channel): D,130
   Electrode[1](name, channel): 2,131
Number of waves (columns): ,7
Number of samples (rows): ,3
t_dws,t_secs,t_usecs,t_ref,RV(D-2)_c0,RV(D-2)_c0_ds,RV(D-2)_c0_ps,RV(2-3)_c1,RV(2-3)_c1_ds,RV(2-3)_c1_ps
 11:40:50.960,1712835650,960324,0,0.0215,0,0,0.0940,0,0
 11:40:50.961,1712835650,960824,0.0005,0.0351,0,0,0.0483,0,0
 11:40:50.961,1712835650,961324,0.0010,0.0493,0,0,-0.0114,0,0
"""


def test_parses_channels_dropping_ds_ps():
    w = parse_ensite_waveforms(_WF, name="EP_Catheter_Bipolar_Waveforms_Filtered")
    # base channels only — the _ds / _ps flag columns are dropped
    assert w.channels == ["RV(D-2)_c0", "RV(2-3)_c1"]
    assert w.data.shape == (3, 2)
    np.testing.assert_allclose(w.data[:, 0], [0.0215, 0.0351, 0.0493])
    np.testing.assert_allclose(w.data[:, 1], [0.0940, 0.0483, -0.0114])


def test_derives_time_and_sample_rate():
    w = parse_ensite_waveforms(_WF)
    np.testing.assert_allclose(w.time, [0.0, 0.0005, 0.0010])
    assert w.sample_rate == 2000.0  # 0.5 ms steps


def test_signal_type_and_metadata():
    w = parse_ensite_waveforms(_WF, name="EP_Catheter_Bipolar_Waveforms_Filtered")
    assert w.signal_type == "egm_bipolar"
    assert w.meta["segment"] == "Stim LA"
    assert w.meta["study_guid"] == "b180"
    assert w.meta["filters"] == {"Highpass": "30 Hz", "Lowpass": "300 Hz", "Notch": "NT_ON"}


def test_bytes_input():
    w = parse_ensite_waveforms(_WF.encode(), name="ecg")
    assert w.data.shape == (3, 2)
