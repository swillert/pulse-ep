"""WaveformStore — Parquet round-trip, columnar projection, time slicing."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.waveform import FilesystemStore, Waveform


def _wave(n=100):
    rng = np.arange(n, dtype=float)
    data = np.column_stack([rng, rng * 2, rng * 3])  # 3 channels
    return Waveform(
        data=data,
        channels=["CS_1_2", "ABL_D", "RV_1"],
        sample_rate=1000.0,
        signal_type="egm_bipolar",
        time=rng / 1000.0,
        meta={"highpass_hz": 30, "lowpass_hz": 300, "segment": "Stim LA"},
    )


def test_roundtrip_preserves_everything(tmp_path):
    store = FilesystemStore(tmp_path)
    uri = store.write(_wave(), key="study_7/wave_1")
    assert uri == "study_7/wave_1.parquet"
    assert (tmp_path / uri).is_file()

    back = store.read(uri)
    w = _wave()
    np.testing.assert_array_equal(back.data, w.data)
    assert back.channels == w.channels
    assert back.sample_rate == 1000.0
    assert back.signal_type == "egm_bipolar"
    assert back.meta["segment"] == "Stim LA"
    np.testing.assert_allclose(back.time, w.time)


def test_columnar_channel_projection(tmp_path):
    store = FilesystemStore(tmp_path)
    uri = store.write(_wave(), key="s/w")
    back = store.read(uri, channels=["ABL_D"])
    assert back.channels == ["ABL_D"]
    assert back.data.shape == (100, 1)
    np.testing.assert_array_equal(back.data[:, 0], np.arange(100.0) * 2)


def test_time_range_slicing(tmp_path):
    store = FilesystemStore(tmp_path)
    uri = store.write(_wave(), key="s/w")
    back = store.read(uri, time_range=(0.010, 0.020))  # seconds → samples 10..20
    assert back.time.min() >= 0.010 and back.time.max() <= 0.020
    assert back.data.shape[0] == back.time.shape[0]


def test_file_is_standard_parquet_readable_by_pandas(tmp_path):
    # proves the on-disk format is portable (pandas/arrow → R/MATLAB/… too)
    import pandas as pd

    store = FilesystemStore(tmp_path)
    uri = store.write(_wave(), key="s/w")
    df = pd.read_parquet(tmp_path / uri)
    assert {"CS_1_2", "ABL_D", "RV_1"}.issubset(df.columns)
    assert len(df) == 100
