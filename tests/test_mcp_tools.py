"""The MCP tools: what they answer, and what they refuse to dump.

A model's context is the scarce resource here. A mesh is tens of thousands of
vertices and a signal window is 2500 samples of 78 channels; a tool that
returns those has answered nothing and left no room to reason. These tests pin
the shaping that keeps the answers usable.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from pulse_ep.core.waveform import Waveform, _to_table
from pulse_ep.mcp.anonymize import REDACTED, Anonymiser
from pulse_ep.mcp.tools import Tools

REAL = "10054321_XY_AB 01_02_2020 09-15-00"


def _parquet_bytes(wave: Waveform) -> bytes:
    import io

    import pyarrow.parquet as pq

    buffer = io.BytesIO()
    pq.write_table(_to_table(wave), buffer)
    return buffer.getvalue()


def _window(n=2500, rate=1000.0):
    """A CARTO-shaped window: 2.5 s, three channels, one annotated point."""
    t = np.arange(n)
    data = np.column_stack(
        [
            np.sin(t / 50.0),  # M1
            np.zeros(n),  # CS1
            np.linspace(-1.0, 1.0, n),  # CS1-CS2
        ]
    )
    # a spike at an index no decimation stride lands on, so it is visible
    # only to statistics that see every sample
    data[1001, 0] = 9.0
    return Waveform(
        data=data,
        channels=["M1", "CS1", "CS1-CS2"],
        sample_rate=rate,
        signal_type="ecg",
        time=13500280 + t.astype(float),
        meta={
            "map_name": "2-RA SR",
            "points": [
                {
                    "point_id": "1",
                    "mapping_channels": {
                        "unipolar": "M1",
                        "bipolar": "MCC_Abl_BiPolar_1",
                        "reference": "CS1-CS2",
                    },
                    "annotations": {"reference": 2000, "map": 1904},
                }
            ],
        },
    )


class FakeClient:
    """A pulse-ep server that answers from memory, and records what it was asked."""

    def __init__(self, wave=None):
        self.calls = []
        self._wave = wave or _window()

    def studies(self):
        self.calls.append(("studies", {}))
        return [{"id": 12, "study_name": REAL, "vendor": "carto"}]

    def maps(self, study_id):
        self.calls.append(("maps", {"study_id": study_id}))
        return [
            {
                "id": 1,
                "map_name": "2-1-ReRA Pace posterior",
                "number_of_points": 66,
                "measurement_points": 66,
            }
        ]

    def scalars(self, map_id):
        self.calls.append(("scalars", {"map_id": map_id}))
        return {
            "map_id": map_id,
            "primary": "activation_time",
            "scalars": [
                {
                    "name": "voltage_bipolar",
                    "kind": "voltage_bipolar",
                    "unit": "mV",
                    "min": 0.05,
                    "max": 4.2,
                    "n_valid": 13483,
                    "source": "carto",
                }
            ],
        }

    def attributes(self, map_id):
        return {"attributes": {"atrium": "RA", "operator": "Dr. Someone"}}

    def areas(self, map_id, intervals, scalar_name=None, distance=5):
        self.calls.append(
            ("areas", {"map_id": map_id, "intervals": intervals, "distance": distance})
        )
        return {"areas": [12.5]}

    def compare(self, map_a_id, map_b_id, scalar_name, **options):
        self.calls.append(("compare", {"a": map_a_id, "b": map_b_id, **options}))
        return {
            "metric": options.get("metric", "euclidean"),
            "scalar_name": scalar_name,
            "n_masked": 3,
            "stats": {"mean": 0.4, "max": 2.1},
        }

    def points(self, map_id, limit=500, offset=0):
        self.calls.append(("points", {"map_id": map_id, "limit": limit, "offset": offset}))
        rows = [
            {
                "point_index": i,
                "source_id": str(i + 1),
                "position": [float(i), 1.0, 2.0],
                "measurements": {"voltage_bipolar": 0.5 + i, "activation_time": -10.0 * i},
                "annotations": {"start_time": 13500280 + i, "reference": 2000, "map": 2000 - i},
                "tags": ["Scar"] if i == 0 else [],
            }
            for i in range(5)
        ]
        page = rows if limit == 0 else rows[offset : offset + limit]
        return {
            "map_id": map_id,
            "count": len(rows),
            "offset": offset,
            "returned": len(page),
            "units": {"voltage_bipolar": "mV", "activation_time": "ms"},
            "points": page,
        }

    def mesh_raw(self, map_id, scalar_name=None):
        self.calls.append(("mesh_raw", {"map_id": map_id, "scalar_name": scalar_name}))
        return {
            "schema_version": "1.0",
            "representation": "raw",
            "scalar_name": scalar_name or "voltage_bipolar",
            "map": {
                "name": "2-1-ReRA Pace posterior",
                "study_name": REAL,
                "mesh_file": "/data/uksh/2-1-ReRA Pace posterior.mesh",
            },
            "study": {"id": 12, "name": REAL},
            "mesh_data": {
                "vertices": [[0.0, 0.0, 0.0]] * 4,
                "faces": [[0, 1, 2], [1, 3, 2]],
                "scalar_fields": {
                    "voltage_bipolar": {"values": [1.0] * 4, "kind": "voltage_bipolar"}
                },
            },
            "point_data": {"measurement_points": [{"position": [0.0, 0.0, 0.0]}] * 5},
            "waveforms": [{"id": 1, "data_uri": "some study/P1.parquet"}],
        }

    def waveforms(self, map_id):
        self.calls.append(("waveforms", {"map_id": map_id}))
        return {
            "map_id": map_id,
            "count": 3,
            "waveforms": [
                {
                    "id": i,
                    "study_id": 12,
                    "map_id": map_id,
                    "point_source_id": str(i),
                    "signal_type": "ecg",
                    "sample_rate": 1000.0,
                    "n_samples": 2500,
                    "n_channels": 3,
                    "channels": ["M1", "CS1", "CS1-CS2"],
                    "segment": None,
                    "download_url": f"/waveforms/{i}/download",
                }
                for i in (1, 2, 3)
            ],
        }

    def waveform_bytes(self, waveform_id):
        self.calls.append(("waveform_bytes", {"id": waveform_id}))
        return _parquet_bytes(self._wave)


@pytest.fixture
def tools():
    return Tools(FakeClient(), Anonymiser())


def test_studies_come_back_under_their_alias(tools):
    result = tools.list_studies()
    assert result["anonymized"] is True
    assert result["studies"] == [{"study_id": 12, "study": "study/12", "vendor": "carto"}]
    assert REAL not in repr(result)


def test_map_summary_answers_what_a_map_measured(tools):
    result = tools.map_summary(1)
    assert result["primary_scalar"] == "activation_time"
    assert result["scalars"][0] == {
        "name": "voltage_bipolar",
        "kind": "voltage_bipolar",
        "unit": "mV",
        "min": 0.05,
        "max": 4.2,
        "n_valid": 13483,
    }
    # attributes travel, but the free-text ones do not
    assert result["attributes"]["atrium"] == "RA"
    assert result["attributes"]["operator"] == REDACTED


def test_an_area_states_its_unit(tools):
    """A bare number leaves the reader to guess cm² from mm²."""
    result = tools.area_of_range(1, 0.0, 0.5, scalar_name="voltage_bipolar")
    assert result["area"] == 12.5
    assert result["unit"] == "cm2"
    assert result["distance_threshold_mm"] == 5.0


def test_comparison_never_requests_the_per_vertex_field(tools):
    """13 000 numbers would be the answer to no question anyone asked."""
    result = tools.compare_maps(1, 2, "voltage_bipolar", metric="geodesic")
    assert result["stats"] == {"mean": 0.4, "max": 2.1}
    assert "delta" not in result
    call = dict(tools.client.calls[-1][1])
    assert call["metric"] == "geodesic"


def test_waveform_listing_is_paged_and_summarised(tools):
    result = tools.list_waveforms(1, limit=2)
    assert result["count"] == 3 and result["returned"] == 2
    assert result["channels_available"] == ["CS1", "CS1-CS2", "M1"]
    assert [w["waveform_id"] for w in result["waveforms"]] == [1, 2]

    second = tools.list_waveforms(1, limit=2, offset=2)
    assert [w["waveform_id"] for w in second["waveforms"]] == [3]


def test_reading_a_window_defaults_to_the_annotated_channels(tools):
    """78 anonymous traces are not an answer; the annotated ones are."""
    result = tools.read_waveform(1)
    assert result["channels_returned"] == ["M1", "CS1-CS2"]
    # the point's bipolar channel is not in this (three-channel) fixture
    assert result["channels_unknown"] == ["MCC_Abl_BiPolar_1"]
    assert result["points"][0]["annotations"]["map"] == 1904
    assert result["unit"] == "mV"


def test_a_window_is_decimated_but_its_statistics_are_not(tools):
    """Decimation drops peaks — which is exactly what a reader must not lose."""
    result = tools.read_waveform(1, channels=["M1"], max_samples=100)

    assert result["n_samples_in_window"] == 2500
    assert result["decimation"] == 25
    assert result["samples_returned"] == 100
    assert 9.0 not in result["series"]["M1"]  # the spike falls between samples …
    assert result["stats"]["M1"]["max"] == 9.0  # … and is still reported


def test_a_time_window_is_cut_in_milliseconds_not_samples(tools):
    """At 2 kHz, 500 ms is 1000 samples — treating ms as an index halves it."""
    fast = Tools(FakeClient(_window(n=2000, rate=2000.0)), Anonymiser())
    result = fast.read_waveform(1, channels=["M1"], start_ms=0, end_ms=500, max_samples=10_000)
    assert result["n_samples_in_window"] == 1000


def test_an_unknown_channel_is_reported_not_guessed(tools):
    result = tools.read_waveform(1, channels=["CS1", "NOPE"])
    assert result["channels_returned"] == ["CS1"]
    assert result["channels_unknown"] == ["NOPE"]


def test_every_tool_stamps_the_anonymisation_mode(tools):
    for result in (
        tools.list_studies(),
        tools.list_maps(12),
        tools.map_summary(1),
        tools.area_of_range(1, 0.0, 0.5),
        tools.compare_maps(1, 2, "voltage_bipolar"),
        tools.list_waveforms(1),
        tools.read_waveform(1),
    ):
        assert result["anonymized"] is True


def test_switched_off_the_real_name_comes_through():
    plain = Tools(FakeClient(), Anonymiser(enabled=False))
    result = plain.list_studies()
    assert result["studies"][0]["study"] == REAL
    assert result["anonymized"] is False


# --- loading everything -----------------------------------------------------


def test_points_are_read_inline_and_paged(tools):
    """A few hundred points is a readable answer; a mesh is not."""
    result = tools.read_points(1, limit=2)
    assert result["count"] == 5 and result["returned"] == 2
    assert result["units"]["voltage_bipolar"] == "mV"
    assert result["points"][0]["measurements"]["voltage_bipolar"] == 0.5
    assert result["points"][0]["tags"] == ["Scar"]
    assert result["points"][0]["annotations"]["reference"] == 2000
    assert [p["point_index"] for p in tools.read_points(1, limit=2, offset=4)["points"]] == [4]


def test_fetch_map_writes_the_whole_thing_and_returns_a_path(tmp_path):
    """The full map is available — it just does not travel through the answer."""
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path)
    result = tools.fetch_map(1)

    assert result["path"] == str(tmp_path / "map-1.json")
    assert result["bytes"] > 0
    assert result["n_vertices"] == 4 and result["n_triangles"] == 2
    assert result["scalar_fields"] == ["voltage_bipolar"]
    assert result["n_points"] == 5
    assert "data" not in result  # the payload went to the file, not into the answer

    written = json.loads((tmp_path / "map-1.json").read_text())
    assert written["mesh_data"]["vertices"] == [[0.0, 0.0, 0.0]] * 4


def test_a_written_file_is_anonymised_like_every_other_answer(tmp_path):
    """The model can read the file, so the file has to hold the same line."""
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path)
    tools.list_studies()  # the anonymiser learns the name
    tools.fetch_map(1)

    text = (tmp_path / "map-1.json").read_text()
    assert REAL not in text
    assert "study/12" in text
    assert "/data/uksh" not in text


def test_fetch_map_inline_returns_the_payload_and_its_size(tmp_path):
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path)
    result = tools.fetch_map(1, inline=True)
    assert result["data"]["mesh_data"]["faces"] == [[0, 1, 2], [1, 3, 2]]
    assert result["bytes"] > 0
    assert "path" not in result
    assert not list(tmp_path.iterdir())  # nothing written when asked for inline


def test_fetch_points_writes_every_point_as_csv(tmp_path):
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path)
    result = tools.fetch_points(1)

    assert result["count"] == 5
    assert result["columns"] == [
        "point_index",
        "source_id",
        "x",
        "y",
        "z",
        "activation_time",
        "voltage_bipolar",
        # the components the value was derived from, as their own group
        "annotation_map",
        "annotation_reference",
        "annotation_start_time",
        "tags",
    ]
    rows = list(csv.reader((tmp_path / "map-1-points.csv").read_text().splitlines()))
    assert rows[0] == result["columns"]
    assert len(rows) == 6  # header + five points
    assert rows[1][5:7] == ["-0.0", "0.5"]
    assert rows[1][7:10] == ["2000", "2000", "13500280"]  # map, reference, start_time
    assert rows[1][10] == "Scar"
    # every point, in one call — no paging for something meant to be computed with
    assert tools.client.calls[-1][1]["limit"] == 0


def test_fetch_waveform_writes_the_stored_parquet(tmp_path):
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path)
    result = tools.fetch_waveform(7)

    path = tmp_path / "waveform-7.parquet"
    assert result["path"] == str(path) and path.is_file()
    assert result["n_samples"] == 2500 and result["n_channels"] == 3
    assert result["sample_rate"] == 1000.0
    # it is the real file: it reads back as a waveform
    from pulse_ep.core.waveform import waveform_from_parquet

    assert waveform_from_parquet(path).channels == ["M1", "CS1", "CS1-CS2"]


def test_a_filename_cannot_escape_the_download_directory(tmp_path):
    """The name is an argument from the model; the directory is not."""
    tools = Tools(FakeClient(), Anonymiser(), download_dir=tmp_path / "downloads")
    result = tools.fetch_points(1, filename="../../etc/passwd")

    written = Path(result["path"])
    assert written.parent == tmp_path / "downloads"
    assert written.name == "passwd"  # the basename, and nothing of the path
    assert not (tmp_path / "etc").exists()
