"""Opt-in waveform ingest: plan -> parse -> Parquet store -> WaveformModel row."""

from __future__ import annotations

from pulse_ep.core.importers.plan import ImportPlan, StudyPlan, WaveformPlan
from pulse_ep.core.importers.source import DirSource
from pulse_ep.core.models import ingest_waveforms
from pulse_ep.core.waveform import FilesystemStore

_WF = """Export Data Element: EP_Catheter_Bipolar_Waveforms_Filtered
Exported from Software Version: 3.0.1
Export from Study: b180
Export from Segment: Stim LA
Highpass: 30 Hz
Lowpass: 300 Hz
Notch: NT_ON
Number of waves (columns): ,7
Number of samples (rows): ,3
t_dws,t_secs,t_usecs,t_ref,RV(D-2)_c0,RV(D-2)_c0_ds,RV(D-2)_c0_ps,RV(2-3)_c1,RV(2-3)_c1_ds,RV(2-3)_c1_ps
 11:40:50.960,1712835650,960324,0,0.0215,0,0,0.0940,0,0
 11:40:50.961,1712835650,960824,0.0005,0.0351,0,0,0.0483,0,0
 11:40:50.961,1712835650,961324,0.0010,0.0493,0,0,-0.0114,0,0
"""

_WF_NAME = "EP_Catheter_Bipolar_Waveforms_Filtered.csv"


def _plan(include: bool) -> ImportPlan:
    return ImportPlan(
        studies=[
            StudyPlan(
                study_name="b180",
                vendor="ensite",
                waveforms=WaveformPlan(files=[_WF_NAME], include=include),
            )
        ]
    )


def test_ingest_stores_waveform_and_builds_row(tmp_path):
    (tmp_path / _WF_NAME).write_text(_WF)
    src = DirSource(tmp_path)
    store = FilesystemStore(tmp_path / "store")

    rows = ingest_waveforms(_plan(include=True), src, store, study_id=42)

    assert len(rows) == 1
    row = rows[0]
    assert row.study_id == 42
    assert row.signal_type == "egm_bipolar"
    assert row.n_samples == 3 and row.n_channels == 2
    assert row.segment == "Stim LA"
    assert row.data_format == "parquet"
    assert row.data_uri.endswith(".parquet")

    # the samples really landed in the store and read back
    back = store.read(row.data_uri)
    assert back.channels == ["RV(D-2)_c0", "RV(2-3)_c1"]
    assert back.data.shape == (3, 2)


def test_ingest_skips_when_opt_out(tmp_path):
    (tmp_path / _WF_NAME).write_text(_WF)
    store = FilesystemStore(tmp_path / "store")
    rows = ingest_waveforms(_plan(include=False), DirSource(tmp_path), store)
    assert rows == []
    assert not (tmp_path / "store").exists()  # nothing written when opt-out
