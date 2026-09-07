"""The import queue lifecycle: enqueue -> prepare -> (review) -> commit.

Sits on the vendor prepare/commit engine and the :class:`ImportJobModel`
state machine. The watcher and the REST/review UI are thin layers on top:
they only create jobs, read/edit ``job.plan``, and call these functions.
"""

from __future__ import annotations

from pulse_ep.core.importers.base import (
    commit_plan,
    detect_vendor,
    get_importer,
    prepare_plan,
)
from pulse_ep.core.importers.plan import ImportPlan, plan_from_dict, plan_to_dict
from pulse_ep.core.importers.source import source_for
from pulse_ep.core.models import (
    JOB_DETECTED,
    JOB_DONE,
    JOB_ERROR,
    JOB_IMPORTING,
    JOB_NEEDS_REVIEW,
    EPMapModel,
    ImportJobModel,
    StudyModel,
    ingest_waveforms,
    persist_study,
)


def enqueue(session, path: str) -> ImportJobModel:
    """Register a detected export bundle. Auto-detects the vendor."""
    try:
        importer = detect_vendor(source_for(path))
    except Exception as exc:  # unreadable / not a dir-or-zip
        importer = None
        detect_error = str(exc)
    else:
        detect_error = None if importer else "no vendor detected"

    job = ImportJobModel(
        source_path=str(path),
        vendor=importer.name if importer else None,
        status=JOB_DETECTED if importer else JOB_ERROR,
        error=detect_error,
    )
    session.add(job)
    session.commit()
    return job


def prepare_job(session, job: ImportJobModel) -> ImportJobModel:
    """Run the cheap dry-run and store the proposed plan for review."""
    try:
        importer = get_importer(job.vendor)
        if importer is None:
            raise ValueError(f"no importer for vendor {job.vendor!r}")
        plan = prepare_plan(importer, source_for(job.source_path))
        job.plan = plan_to_dict(plan)
        job.status = JOB_NEEDS_REVIEW
        job.error = None
    except Exception as exc:
        job.status = JOB_ERROR
        job.error = str(exc)
    session.commit()
    return job


def _waveform_store():
    """The configured waveform store, or ``None`` when none is set up."""
    from pulse_ep.core.config import get_settings
    from pulse_ep.core.waveform import FilesystemStore

    root = (get_settings().waveform_store_dir or "").strip()
    return FilesystemStore(root) if root else None


def commit_job(session, job: ImportJobModel) -> ImportJobModel:
    """Execute the (reviewer-edited) plan and persist it.

    Idempotent by study identity: a study already in the database is *not*
    written again — the job simply points at the existing one. This is what
    lets the watcher rescan a drop directory without creating duplicates.

    Waveforms are imported here too (when the reviewer opted in), so the queue
    imports exactly what ``pulse-ep-import-ensite`` does. Opting in without a
    configured ``PULSE_EP_WAVEFORM_STORE_DIR`` fails the job *before* anything
    is written, rather than silently dropping the signals.
    """
    job.status = JOB_IMPORTING
    session.commit()
    try:
        importer = get_importer(job.vendor)
        if importer is None:
            raise ValueError(f"no importer for vendor {job.vendor!r}")
        source = source_for(job.source_path)
        plan = plan_from_dict(job.plan or {})

        wanted = {sp.study_name: sp for sp in plan.studies if sp.waveforms.include}
        store = _waveform_store() if wanted else None
        if wanted and store is None:
            raise ValueError(
                "waveforms were selected but no waveform store is configured "
                "(set PULSE_EP_WAVEFORM_STORE_DIR)"
            )

        study_ids: list[int] = []
        for study in commit_plan(importer, plan, source):
            existing = StudyModel.find_by_name(study.name, session)
            if existing is not None:
                study_ids.append(existing.id)
                continue
            model = persist_study(session, study)
            study_ids.append(model.id)

            sp = wanted.get(study.name)
            if sp is not None:
                # Per-point signals belong to the map they were acquired on;
                # the ids only exist once the study is persisted.
                session.flush()
                map_ids = {
                    m.map_name: m.id
                    for m in session.query(EPMapModel).filter_by(study_id=model.id).all()
                }
                for row in ingest_waveforms(
                    ImportPlan(studies=[sp]), source, store, study_id=model.id, map_ids=map_ids
                ):
                    session.add(row)

        job.study_id = study_ids[0] if study_ids else None
        job.status = JOB_DONE
        job.error = None
    except Exception as exc:
        session.rollback()
        job.status = JOB_ERROR
        job.error = str(exc)
    session.commit()
    return job


__all__ = [
    "JOB_DETECTED",
    "JOB_NEEDS_REVIEW",
    "JOB_IMPORTING",
    "JOB_DONE",
    "JOB_ERROR",
    "enqueue",
    "prepare_job",
    "commit_job",
]
