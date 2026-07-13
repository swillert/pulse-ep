"""Import-queue REST serialisation (route behaviour is smoke-tested vs Postgres)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

from pulse_ep.server.import_api import job_detail, job_summary  # noqa: E402


def _job():
    return SimpleNamespace(
        id=1,
        source_path="/drop/exp",
        vendor="ensite",
        status="needs_review",
        study_id=None,
        error=None,
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        updated_at=None,
        plan={"studies": [{"study_name": "s"}]},
    )


def test_job_summary_serialises_dates_and_fields():
    s = job_summary(_job())
    assert s["id"] == 1 and s["vendor"] == "ensite" and s["status"] == "needs_review"
    assert s["created_at"] == "2026-01-02T03:04:05"
    assert s["updated_at"] is None
    assert "plan" not in s  # summary omits the (large) plan


def test_job_detail_includes_plan():
    d = job_detail(_job())
    assert d["plan"] == {"studies": [{"study_name": "s"}]}
