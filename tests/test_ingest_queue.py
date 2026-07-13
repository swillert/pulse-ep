"""Import queue: plan (de)serialisation + enqueue vendor detection.

The full DB lifecycle (enqueue -> prepare -> commit) is exercised manually
against Postgres; here we cover the parts that need no live session.
"""

from __future__ import annotations

from pulse_ep.core.importers.plan import (
    ImportPlan,
    MapPlan,
    StudyPlan,
    WaveformPlan,
    plan_from_dict,
    plan_to_dict,
)
from pulse_ep.core.ingest_queue import enqueue
from pulse_ep.core.models import JOB_ERROR


def test_plan_roundtrip_preserves_reviewer_selections():
    plan = ImportPlan(
        studies=[
            StudyPlan(
                study_name="s",
                vendor="ensite",
                provenance={"software_version": "6.0"},
                maps=[
                    MapPlan(
                        map_name="m",
                        files=["a.xml"],
                        part="endo",
                        scalar_fields={"voltage_bipolar": "voltage_bipolar"},
                        n_vertices=100,
                        points_files=["Map_PP_bi.csv"],
                        include=True,
                        include_points=False,  # a reviewer edit
                    )
                ],
                waveforms=WaveformPlan(files=["w.csv"], estimated_bytes=123, include=True),
                placed_point_files=["Lesions.csv"],
                include_placed_points=False,
                anatomy_files=["Model_Groups.xml"],
                include_anatomy=True,
            )
        ]
    )
    back = plan_from_dict(plan_to_dict(plan))
    sp = back.studies[0]
    assert sp.study_name == "s" and sp.vendor == "ensite"
    m = sp.maps[0]
    assert m.part == "endo" and m.points_files == ["Map_PP_bi.csv"]
    assert m.include_points is False  # edit survived the round-trip
    assert sp.waveforms.include is True and sp.waveforms.estimated_bytes == 123
    assert sp.include_placed_points is False and sp.placed_point_files == ["Lesions.csv"]
    assert sp.include_anatomy is True


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def test_enqueue_detects_vendor(tmp_path):
    # a .mesh file makes it look like CARTO
    (tmp_path / "1-Map.mesh").write_text("#TriangulatedMeshVersion2.0")
    job = enqueue(FakeSession(), str(tmp_path))
    assert job.vendor == "carto" and job.status == "detected"


def test_enqueue_unknown_vendor_is_error(tmp_path):
    (tmp_path / "random.txt").write_text("x")
    job = enqueue(FakeSession(), str(tmp_path))
    assert job.vendor is None and job.status == JOB_ERROR
