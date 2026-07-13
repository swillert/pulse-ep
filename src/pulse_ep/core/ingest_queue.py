"""The import queue lifecycle: enqueue -> prepare -> (review) -> commit.

Sits on the vendor prepare/commit engine and the :class:`ImportJobModel`
state machine. The watcher and the REST/review UI are thin layers on top:
they only create jobs, read/edit ``job.plan``, and call these functions.
"""

from __future__ import annotations

from pulse_ep.core.importers.base import detect_vendor, get_importer
from pulse_ep.core.importers.plan import plan_from_dict, plan_to_dict
from pulse_ep.core.importers.source import source_for
from pulse_ep.core.models import (
    JOB_DETECTED,
    JOB_DONE,
    JOB_ERROR,
    JOB_IMPORTING,
    JOB_NEEDS_REVIEW,
    ImportJobModel,
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
        plan = importer.prepare(source_for(job.source_path))
        job.plan = plan_to_dict(plan)
        job.status = JOB_NEEDS_REVIEW
        job.error = None
    except Exception as exc:
        job.status = JOB_ERROR
        job.error = str(exc)
    session.commit()
    return job


def commit_job(session, job: ImportJobModel) -> ImportJobModel:
    """Execute the (reviewer-edited) plan and persist it. Idempotent-ish:
    a study already present is left to :func:`persist_study`'s caller policy."""
    job.status = JOB_IMPORTING
    session.commit()
    try:
        importer = get_importer(job.vendor)
        if importer is None:
            raise ValueError(f"no importer for vendor {job.vendor!r}")
        source = source_for(job.source_path)
        plan = plan_from_dict(job.plan or {})
        studies = importer.commit(plan, source)
        study_ids = [persist_study(session, s).id for s in studies]
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
