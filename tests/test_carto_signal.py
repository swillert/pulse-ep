"""CARTO's per-point ECG windows: parse, link to their point, store.

These were never imported at all — ``point_importer`` said "ECG data is NOT
imported (too large for DB storage)", which was true of the relational DB and
not of the WaveformStore the samples actually go to.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.importers.carto import CartoImporter, _waveform_plan
from pulse_ep.core.importers.carto_signal import (
    ecg_start_time,
    iter_waveforms,
    parse_carto_ecg_export,
    parse_point_export,
    point_index,
)
from pulse_ep.core.importers.plan import ImportPlan, StudyPlan, WaveformPlan
from pulse_ep.core.importers.source import DirSource
from pulse_ep.core.models import ingest_waveforms
from pulse_ep.core.waveform import FilesystemStore

MAP = "1-LA Sinus"
START = 13140188

_CHANNELS = ["M1(1)", "M2(2)", "CS1(11)", "CS2(12)", "CS1-CS2(101)", "MCC_Abl_BiPolar_1(190)"]

_POINT_XML = f"""<Point ID="1000" Date="04/12/24" Time="10:39:32">
    <Annotations StartTime="{START}" Reference_Annotation="2000" Map_Annotation="1926" />
    <WOI From="-170" To="146" />
    <Voltages Unipolar="1.601" Bipolar="0.605" />
    <ECG FileName="{MAP}_ECG_Export_{START}.txt" UnipolarMappingChannel="M1"
         BipolarMappingChannel="MCC_Abl_BiPolar_1" ReferenceChannel="CS1-CS2" />
</Point>
"""


def _ecg_text(n_samples: int = 4, gain: float = 0.003) -> str:
    header = "".join(f"{c:<30s}" for c in _CHANNELS)
    rows = [
        "".join(f"{v:<30d}" for v in (i, -i, 2 * i, -2 * i, 100 + i, 1000 + i))
        for i in range(n_samples)
    ]
    return "\n".join(["ECG_Export_4.1", f"Raw ECG to MV (gain) = {gain:.6f}", header, *rows]) + "\n"


@pytest.fixture
def export(tmp_path):
    """A miniature CARTO export: one ECG window and the point that owns it."""
    (tmp_path / f"{MAP}_ECG_Export_{START}.txt").write_text(_ecg_text(), encoding="latin-1")
    (tmp_path / f"{MAP}_P1000_Point_Export.xml").write_text(_POINT_XML, encoding="utf-8")
    return tmp_path


def test_samples_are_scaled_to_millivolts(export):
    name = f"{MAP}_ECG_Export_{START}.txt"
    wave = parse_carto_ecg_export((export / name).read_bytes(), name=name)

    assert wave.channels == ["M1", "M2", "CS1", "CS2", "CS1-CS2", "MCC_Abl_BiPolar_1"]
    assert wave.data.shape == (4, 6)
    assert wave.sample_rate == 1000.0
    # raw counts times the header's gain — not the counts themselves
    assert np.allclose(wave.data[:, 4], [0.300, 0.303, 0.306, 0.309])
    assert wave.meta["gain_mv"] == 0.003
    assert wave.meta["channel_ids"]["CS1-CS2"] == 101


def test_the_scaled_samples_declare_millivolts(export):
    """The gain is applied here, so the unit is a fact — and now recorded.

    It could stay a convention while the store held only electrograms. It
    cannot now that forces in grams and positions in millimetres go into the
    same Parquet store.
    """
    from pulse_ep.core.importers.carto_signal import parse_carto_ecg_export

    name = f"{MAP}_ECG_Export_{START}.txt"
    wave = parse_carto_ecg_export((export / name).read_bytes(), name=name)
    assert wave.units == ["mV"] * len(wave.channels)
    assert len(wave.units) == wave.data.shape[1]


def test_time_is_the_study_clock(export):
    """Windows from different points must land on one axis, not each on 0."""
    name = f"{MAP}_ECG_Export_{START}.txt"
    wave = parse_carto_ecg_export((export / name).read_bytes(), name=name)
    assert wave.time is not None
    assert wave.time[0] == START and wave.time[-1] == START + 3
    assert ecg_start_time(f"x/{MAP}_ECG_Export_{START}.txt") == START


def test_a_truncated_row_is_dropped_not_padded(export):
    text = _ecg_text() + "7\n"  # an export interrupted mid-write
    wave = parse_carto_ecg_export(text, name=f"{MAP}_ECG_Export_{START}.txt")
    assert wave.data.shape == (4, 6)  # the short row would have shifted every channel


def test_a_file_that_is_not_an_ecg_export_is_refused():
    with pytest.raises(ValueError):
        parse_carto_ecg_export("t_dws,RV(D-2)\n1,2\n3,4\n5,6\n", name="ensite.csv")


def test_point_export_yields_the_mapping_channels(export):
    info = parse_point_export(_POINT_XML)
    assert info["point_id"] == "1000"
    assert info["channels"] == {
        "unipolar": "M1",
        "bipolar": "MCC_Abl_BiPolar_1",
        "reference": "CS1-CS2",
    }
    assert info["annotations"]["reference"] == 2000
    assert info["annotations"]["woi_from"] == -170
    # a study catalogue is not a point export
    assert parse_point_export("<Study Name='x'/>") is None
    assert parse_point_export("not xml at all") is None


def test_index_links_a_window_to_its_point(export):
    index = point_index(DirSource(export))
    assert set(index) == {f"{MAP}_ECG_Export_{START}.txt"}
    assert [p["point_id"] for p in index[f"{MAP}_ECG_Export_{START}.txt"]] == ["1000"]


def test_stored_window_carries_what_makes_it_readable(export, tmp_path):
    """78 anonymous traces are not a measurement — which channel was annotated is."""
    plan = StudyPlan(
        study_name="S",
        vendor="carto",
        waveforms=WaveformPlan(files=[f"{MAP}_ECG_Export_{START}.txt"], include=True),
    )
    store = FilesystemStore(tmp_path / "store")
    rows = ingest_waveforms(
        ImportPlan(studies=[plan]), DirSource(export), store, study_id=7, map_ids={MAP: 3}
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.study_id == 7
    assert row.point_source_id == "1000"  # the point, not just a timestamp
    assert row.map_id == 3  # and the map it was acquired on
    assert row.n_samples == 4 and row.n_channels == 6
    assert row.data_uri == f"S/{MAP}_ECG_Export_{START}.parquet"

    back = store.read(row.data_uri, channels=["CS1-CS2"])
    assert back.data.shape == (4, 1)
    assert back.meta["points"][0]["mapping_channels"]["reference"] == "CS1-CS2"
    assert back.meta["points"][0]["annotations"]["map"] == 1926


_SECOND_POINT_XML = _POINT_XML.replace('ID="1000"', 'ID="1001"').replace(
    'Map_Annotation="1926"', 'Map_Annotation="1904"'
)


def test_one_window_serves_every_point_taken_from_it(export, tmp_path):
    """A multi-electrode catheter acquires many points from one recording.

    In the reference CARTO export 1934 points share 699 windows — 84 % of
    points in groups of up to ten. Keeping only one point per window (the last
    one read) left most of a real study looking as though nothing had been
    recorded for it.
    """
    (export / f"{MAP}_P1001_Point_Export.xml").write_text(_SECOND_POINT_XML, encoding="utf-8")

    plan = StudyPlan(
        study_name="S",
        vendor="carto",
        waveforms=WaveformPlan(files=[f"{MAP}_ECG_Export_{START}.txt"], include=True),
    )
    store = FilesystemStore(tmp_path / "store")
    rows = ingest_waveforms(ImportPlan(studies=[plan]), DirSource(export), store, study_id=7)

    # one row per point …
    assert sorted(r.point_source_id for r in rows) == ["1000", "1001"]
    # … all referring to a single stored copy of the samples
    assert len({r.data_uri for r in rows}) == 1
    assert len(list((tmp_path / "store" / "S").glob("*.parquet"))) == 1

    # and the file knows both points, with each one's own annotation
    back = store.read(rows[0].data_uri)
    assert [p["point_id"] for p in back.meta["points"]] == ["1000", "1001"]
    assert [p["annotations"]["map"] for p in back.meta["points"]] == [1926, 1904]


def test_a_window_without_its_point_xml_still_imports(export, tmp_path):
    (export / f"{MAP}_P1000_Point_Export.xml").unlink()
    stems = list(
        iter_waveforms(
            StudyPlan(
                study_name="S",
                vendor="carto",
                waveforms=WaveformPlan(files=[f"{MAP}_ECG_Export_{START}.txt"]),
            ),
            DirSource(export),
        )
    )
    stem, wave, point_id, map_name = stems[0]
    assert point_id is None
    assert map_name == MAP
    assert stem == f"{MAP}_ECG_Export_{START}"
    assert wave.data.shape == (4, 6)


def test_the_plan_offers_signals_but_does_not_select_them(export):
    plan = _waveform_plan(DirSource(export), [MAP])
    assert plan.files == [f"{MAP}_ECG_Export_{START}.txt"]
    assert plan.estimated_bytes > 0
    assert plan.include is False  # opt-in: a real export is gigabytes of these


def test_the_plan_takes_only_this_study_s_maps(export):
    (export / "Other Map_ECG_Export_999.txt").write_text(_ecg_text(), encoding="latin-1")
    assert _waveform_plan(DirSource(export), [MAP]).files == [f"{MAP}_ECG_Export_{START}.txt"]


def test_carto_importer_sniffs_no_mesh_here(export):
    """Guard the fixture: without a .mesh this is not a CARTO export to sniff."""
    assert CartoImporter().sniff(DirSource(export)) is False
