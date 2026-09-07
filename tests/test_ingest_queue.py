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


# --- vendors without a prepare/commit refinement ---------------------------
#
# Both shipped importers now implement prepare/commit, so these exercise the
# mechanism with a stand-in: the queue must carry a future parse-only vendor
# instead of dying on a missing method.


class _ParseOnly:
    name = "parse-only"

    def __init__(self, studies=()):
        self._studies = list(studies)

    def sniff(self, source):
        return True

    def parse(self, source):
        return self._studies


def test_prepare_plan_falls_back_for_a_parse_only_importer():
    from pulse_ep.core.importers.base import prepare_plan

    plan = prepare_plan(_ParseOnly(), object())
    assert plan.studies == []
    assert plan.issues and "parse-only" in plan.issues[0]


def test_both_shipped_importers_offer_a_reviewable_plan():
    """Regression: CARTO used to have no ``prepare`` at all, so every CARTO
    bundle in the drop directory failed with an AttributeError."""
    from pulse_ep.core.importers.carto import CartoImporter
    from pulse_ep.core.importers.ensite import EnsiteImporter

    for importer in (CartoImporter(), EnsiteImporter()):
        assert callable(getattr(importer, "prepare", None)), importer.name
        assert callable(getattr(importer, "commit", None)), importer.name


def test_commit_plan_falls_back_to_parse():
    from pulse_ep.core.importers.base import commit_plan

    sentinel = [object()]

    class ParseOnly:
        name = "parse-only"

        def sniff(self, source):
            return True

        def parse(self, source):
            return sentinel

    assert commit_plan(ParseOnly(), ImportPlan(), object()) is sentinel


def test_commit_plan_prefers_an_importer_that_has_one():
    from pulse_ep.core.importers.base import commit_plan

    class WithCommit:
        name = "with-commit"

        def sniff(self, source):
            return True

        def parse(self, source):
            raise AssertionError("parse must not be used when commit exists")

        def commit(self, plan, source):
            return ["committed"]

    assert commit_plan(WithCommit(), ImportPlan(), object()) == ["committed"]


def test_fallback_plan_survives_the_json_roundtrip():
    """The review UI stores the plan as JSON before commit reads it back."""
    from pulse_ep.core.importers.base import prepare_plan

    back = plan_from_dict(plan_to_dict(prepare_plan(_ParseOnly(), object())))
    assert back.studies == [] and back.issues


# --- commit_job: duplicate guard + waveform parity ------------------------


class _FakeSession:
    """Enough of a session for commit_job: it adds rows and looks up map ids."""

    def __init__(self, maps=()):
        self.added = []
        self._maps = list(maps)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass

    def rollback(self):
        pass

    def flush(self):
        pass

    def query(self, _model):
        return self

    def filter_by(self, **_kwargs):
        return self

    def all(self):
        return self._maps


def _job(plan):
    from types import SimpleNamespace

    return SimpleNamespace(
        vendor="fake",
        source_path="/x",
        plan=plan_to_dict(plan),
        status=None,
        study_id=None,
        error=None,
    )


def _patch_commit_job(monkeypatch, studies, existing=None, persisted=None):
    """Stub out everything commit_job touches that needs a live database."""
    from types import SimpleNamespace

    from pulse_ep.core import ingest_queue as q

    importer = SimpleNamespace(
        name="fake",
        sniff=lambda s: True,
        parse=lambda s: studies,
        commit=lambda p, s: studies,
    )
    monkeypatch.setattr(q, "get_importer", lambda v: importer)
    monkeypatch.setattr(q, "source_for", lambda p: object())
    monkeypatch.setattr(
        q.StudyModel, "find_by_name", classmethod(lambda cls, name, session: existing)
    )
    sink = persisted if persisted is not None else []

    def _persist(session, study):
        sink.append(study)
        return SimpleNamespace(id=7)

    monkeypatch.setattr(q, "persist_study", _persist)
    return q


def test_commit_job_does_not_reimport_an_existing_study(monkeypatch):
    from types import SimpleNamespace

    from pulse_ep.core.models import JOB_DONE

    persisted = []
    q = _patch_commit_job(
        monkeypatch,
        studies=[SimpleNamespace(name="already-there")],
        existing=SimpleNamespace(id=42),
        persisted=persisted,
    )
    job = _job(ImportPlan(studies=[StudyPlan(study_name="already-there", vendor="fake")]))
    q.commit_job(_FakeSession(), job)

    assert persisted == []  # nothing written a second time
    assert job.study_id == 42 and job.status == JOB_DONE


def test_commit_job_persists_a_new_study(monkeypatch):
    from types import SimpleNamespace

    from pulse_ep.core.models import JOB_DONE

    persisted = []
    q = _patch_commit_job(
        monkeypatch, studies=[SimpleNamespace(name="fresh")], existing=None, persisted=persisted
    )
    job = _job(ImportPlan(studies=[StudyPlan(study_name="fresh", vendor="fake")]))
    q.commit_job(_FakeSession(), job)

    assert [s.name for s in persisted] == ["fresh"]
    assert job.study_id == 7 and job.status == JOB_DONE


def test_commit_job_refuses_waveforms_without_a_store(monkeypatch):
    """Failing up front beats persisting the maps and dropping the signals."""
    from types import SimpleNamespace

    from pulse_ep.core.models import JOB_ERROR as ERR

    persisted = []
    q = _patch_commit_job(
        monkeypatch, studies=[SimpleNamespace(name="s")], existing=None, persisted=persisted
    )
    monkeypatch.setattr(q, "_waveform_store", lambda: None)
    job = _job(
        ImportPlan(
            studies=[
                StudyPlan(
                    study_name="s",
                    vendor="fake",
                    waveforms=WaveformPlan(files=["w.csv"], include=True),
                )
            ]
        )
    )
    q.commit_job(_FakeSession(), job)

    assert job.status == ERR and "waveform store" in job.error
    assert persisted == []  # nothing written before the refusal


def test_commit_job_ingests_waveforms_when_a_store_is_configured(monkeypatch):
    from types import SimpleNamespace

    from pulse_ep.core.models import JOB_DONE

    q = _patch_commit_job(monkeypatch, studies=[SimpleNamespace(name="s")], existing=None)
    monkeypatch.setattr(q, "_waveform_store", lambda: "store")
    monkeypatch.setattr(
        q,
        "ingest_waveforms",
        lambda plan, src, store, study_id, map_ids: ["row1", "row2"] if map_ids == {"m": 9} else [],
    )
    job = _job(
        ImportPlan(
            studies=[
                StudyPlan(
                    study_name="s",
                    vendor="fake",
                    waveforms=WaveformPlan(files=["w.csv"], include=True),
                )
            ]
        )
    )
    session = _FakeSession(maps=[SimpleNamespace(map_name="m", id=9)])
    q.commit_job(session, job)

    # the rows are stored, and the per-point windows know which map they are on
    assert session.added == ["row1", "row2"] and job.status == JOB_DONE
