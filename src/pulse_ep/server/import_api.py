"""REST API for the import queue (Flask Blueprint).

Backs the review UI: list jobs, inspect / edit a job's plan, scan the drop
directory, prepare and commit a job. All routes are JWT-protected. Kept in a
blueprint so the monolithic ``app.py`` doesn't grow.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.orm.attributes import flag_modified

from pulse_ep.core.config import get_settings
from pulse_ep.core.database import get_db_session
from pulse_ep.core.ingest_queue import commit_job, enqueue, prepare_job
from pulse_ep.core.ingest_watcher import scan_and_enqueue
from pulse_ep.core.models import ImportJobModel
from pulse_ep.server.roles import writes

import_api = Blueprint("import_api", __name__, url_prefix="/api/import-jobs")


def job_summary(job: ImportJobModel) -> dict:
    return {
        "id": job.id,
        "source_path": job.source_path,
        "vendor": job.vendor,
        "status": job.status,
        "study_id": job.study_id,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def job_detail(job: ImportJobModel) -> dict:
    return {**job_summary(job), "plan": job.plan}


@import_api.get("")
@jwt_required()
def list_jobs():
    status = request.args.get("status")
    with get_db_session() as session:
        query = session.query(ImportJobModel)
        if status:
            query = query.filter_by(status=status)
        jobs = query.order_by(ImportJobModel.id.desc()).all()
        return jsonify([job_summary(j) for j in jobs])


@import_api.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    with get_db_session() as session:
        job = session.get(ImportJobModel, job_id)
        if job is None:
            return jsonify({"msg": "not found"}), 404
        return jsonify(job_detail(job))


@import_api.patch("/<int:job_id>/plan")
@jwt_required()
@writes
def update_plan(job_id: int):
    plan = request.get_json(silent=True)
    if not isinstance(plan, dict):
        return jsonify({"msg": "a plan object is required"}), 400
    with get_db_session() as session:
        job = session.get(ImportJobModel, job_id)
        if job is None:
            return jsonify({"msg": "not found"}), 404
        job.plan = plan
        flag_modified(job, "plan")
        session.commit()
        return jsonify(job_detail(job))


@import_api.post("/scan")
@jwt_required()
@writes
def scan():
    with get_db_session() as session:
        jobs = scan_and_enqueue(session, get_settings().drop_dir)
        return jsonify({"enqueued": [job_summary(j) for j in jobs]}), 201


@import_api.post("")
@jwt_required()
@writes
def enqueue_path():
    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        return jsonify({"msg": "a path is required"}), 400
    with get_db_session() as session:
        return jsonify(job_summary(enqueue(session, path))), 201


@import_api.post("/<int:job_id>/prepare")
@jwt_required()
@writes
def prepare(job_id: int):
    with get_db_session() as session:
        job = session.get(ImportJobModel, job_id)
        if job is None:
            return jsonify({"msg": "not found"}), 404
        return jsonify(job_detail(prepare_job(session, job)))


@import_api.post("/<int:job_id>/commit")
@jwt_required()
@writes
def commit(job_id: int):
    with get_db_session() as session:
        job = session.get(ImportJobModel, job_id)
        if job is None:
            return jsonify({"msg": "not found"}), 404
        return jsonify(job_detail(commit_job(session, job)))
