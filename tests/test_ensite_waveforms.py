"""EnSite waveform CSV parser (preamble + t_dws header + triplet channels)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_waveforms


def test_parses_channels_dropping_ds_ps(ensite_waveform_csv):
    w = parse_ensite_waveforms(ensite_waveform_csv, name="EP_Catheter_Bipolar_Waveforms_Filtered")
    # base channels only — the _ds / _ps flag columns are dropped
    assert w.channels == ["RV(D-2)_c0", "RV(2-3)_c1"]
    assert w.data.shape == (3, 2)
    np.testing.assert_allclose(w.data[:, 0], [0.0215, 0.0351, 0.0493])
    np.testing.assert_allclose(w.data[:, 1], [0.0940, 0.0483, -0.0114])


def test_derives_time_and_sample_rate(ensite_waveform_csv):
    w = parse_ensite_waveforms(ensite_waveform_csv)
    np.testing.assert_allclose(w.time, [0.0, 0.0005, 0.0010])
    assert w.sample_rate == 2000.0  # 0.5 ms steps


def test_signal_type_and_metadata(ensite_waveform_csv):
    w = parse_ensite_waveforms(ensite_waveform_csv, name="EP_Catheter_Bipolar_Waveforms_Filtered")
    assert w.signal_type == "egm_bipolar"
    assert w.meta["segment"] == "Stim LA"
    assert w.meta["study_guid"] == "b180"
    assert w.meta["filters"] == {"Highpass": "30 Hz", "Lowpass": "300 Hz", "Notch": "NT_ON"}


def test_bytes_input(ensite_waveform_csv):
    w = parse_ensite_waveforms(ensite_waveform_csv.encode(), name="ecg")
    assert w.data.shape == (3, 2)
