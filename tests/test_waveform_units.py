"""Per-channel units on stored signals.

The store held only electrograms, which are all millivolts, so the unit could
stay a convention. It cannot once EnSite X's per-timepoint exports live here
too: one ``Contact_Force_Computed`` file carries force in grams, angles in
degrees and cavity distances in millimetres, and a magnetic location export
puts a dimensionless quaternion beside a translation in mm.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.waveform import UNKNOWN_UNIT, FilesystemStore, Waveform, waveform_from_parquet


def _mixed() -> Waveform:
    """The shape a contact-force export has: three units in one file."""
    return Waveform(
        data=np.arange(12, dtype=float).reshape(4, 3),
        channels=["totalForce_0", "alphaAngle_0", "cavityDistance1_0"],
        units=["g", "deg", "mm"],
        sample_rate=50.0,
        signal_type="force",
        time=np.array([0.0, 0.02, 0.04, 0.06]),
    )


def test_units_are_filled_to_the_channel_count():
    """A short or absent list must not push the check onto every reader."""
    w = Waveform(data=np.zeros((2, 3)), channels=["a", "b", "c"])
    assert w.units == [UNKNOWN_UNIT] * 3

    partial = Waveform(data=np.zeros((2, 3)), channels=["a", "b", "c"], units=["mV"])
    assert partial.units == ["mV", UNKNOWN_UNIT, UNKNOWN_UNIT]

    blank = Waveform(data=np.zeros((2, 2)), channels=["a", "b"], units=["", "mm"])
    assert blank.units == [UNKNOWN_UNIT, "mm"]


def test_unit_of_a_named_channel():
    w = _mixed()
    assert w.unit("alphaAngle_0") == "deg"
    assert w.unit("nothing_like_it") == UNKNOWN_UNIT


def test_units_survive_the_parquet_round_trip(tmp_path):
    store = FilesystemStore(tmp_path)
    uri = store.write(_mixed(), "study/1/force")
    back = store.read(uri)
    assert back.channels == ["totalForce_0", "alphaAngle_0", "cavityDistance1_0"]
    assert back.units == ["g", "deg", "mm"]
    assert back.signal_type == "force"


def test_a_projection_takes_its_own_channels_units(tmp_path):
    """Asking for two of three channels must not return the first two units."""
    store = FilesystemStore(tmp_path)
    uri = store.write(_mixed(), "study/1/force")
    back = store.read(uri, channels=["cavityDistance1_0", "totalForce_0"])
    assert back.channels == ["cavityDistance1_0", "totalForce_0"]
    assert back.units == ["mm", "g"]


def test_a_file_written_before_units_existed_reads_back_as_unknown(tmp_path):
    """Additive: an older Parquet file has no units key, and must still load."""
    import json

    import pyarrow.parquet as pq

    store = FilesystemStore(tmp_path)
    uri = store.write(_mixed(), "study/1/force")
    path = tmp_path / uri

    table = pq.read_table(path)
    md = dict(table.schema.metadata or {})
    key = b"pulse_ep_waveform"
    stored = json.loads(md[key])
    del stored["units"]  # as a pre-0.4.4 writer left it
    md[key] = json.dumps(stored).encode()
    pq.write_table(table.replace_schema_metadata(md), path)

    back = waveform_from_parquet(path)
    assert back.channels == ["totalForce_0", "alphaAngle_0", "cavityDistance1_0"]
    assert back.units == [UNKNOWN_UNIT] * 3


def test_the_db_row_records_the_units():
    from pulse_ep.core.models import waveform_row

    row = waveform_row(_mixed(), "study/1/force.parquet")
    assert row.channels == ["totalForce_0", "alphaAngle_0", "cavityDistance1_0"]
    assert row.units == ["g", "deg", "mm"]


def test_the_two_signal_importers_declare_what_they_know():
    """CARTO applies its gain, so millivolts is a fact about the values.

    EnSite X declares neither a unit nor a scale factor anywhere in its export
    preamble, and the parser applies none — the numbers are whatever the system
    wrote. ``unknown`` is the honest answer there, not a placeholder someone
    forgot to fill in.
    """
    from pulse_ep.core.importers.ensite import parse_ensite_waveforms
    from tests.test_ensite_waveforms import _WF

    w = parse_ensite_waveforms(_WF, name="EP_Catheter_Bipolar_Waveforms_Filtered")
    assert w.units == [UNKNOWN_UNIT] * len(w.channels)
    assert len(w.units) == w.data.shape[1]
