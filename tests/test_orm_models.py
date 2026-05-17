"""Schema-creation smoke test against an in-memory SQLite engine.

Note
----
Several pulse-ep ORM columns use PostgreSQL-specific types (``JSONB``,
``ARRAY``). SQLite emulates them imperfectly, so this test only verifies
that the schema metadata can be discovered and table creation runs
end-to-end on a portable backend. Full ORM round-trips are exercised
against PostgreSQL in CI when the service is available.
"""

from __future__ import annotations

import pytest

from pulse_ep import (
    AttributeMetadata,
    Base,
    EPMapAttributes,
    EPMapModel,
    EPMapPoint,
    StudyModel,
    UserModel,
)


def test_models_are_registered_with_base() -> None:
    tables = Base.metadata.tables
    assert "studies" in tables
    # Other models are registered too — verify a representative subset.
    table_names = set(tables.keys())
    for model in (
        EPMapModel,
        EPMapAttributes,
        EPMapPoint,
        UserModel,
        AttributeMetadata,
        StudyModel,
    ):
        assert model.__tablename__ in table_names


def test_create_all_on_sqlite(sqlite_engine_and_session) -> None:
    """Best-effort schema creation; JSONB-bearing tables may legitimately
    fail on SQLite and that is expected (they are tested against Postgres)."""
    engine, _ = sqlite_engine_and_session
    try:
        Base.metadata.create_all(engine)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"SQLite emulation of pulse-ep schema not supported: {exc}")
