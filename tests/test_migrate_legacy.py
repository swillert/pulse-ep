"""Adopting databases that predate the Alembic migrations (``pulse-ep-migrate``)."""

from __future__ import annotations

from pulse_ep.cli.migrate import (
    BASELINE_COLUMNS,
    BASELINE_INDEXES,
    BASELINE_REVISION,
    REVISION_MARKERS,
    legacy_statements,
    revision_present,
)

LEGACY_TABLES = {
    "attribute_metadata",
    "colormaps",
    "ep_map_points",
    "epmap_attributes",
    "epmaps",
    "reports",
    "studies",
    "users",
}
LEGACY_COLUMNS = {
    "studies": {"id", "name"},
    "epmaps": {"id", "study_id", "map_name", "act_bip", "vertices", "triangles"},
}


def test_fresh_database_is_not_legacy():
    assert legacy_statements(set(), {}) is None


def test_migrated_database_is_not_legacy():
    assert legacy_statements(LEGACY_TABLES | {"alembic_version", "waveforms"}, {}) is None


def test_create_all_database_gets_baseline_columns_and_indexes():
    ddl = legacy_statements(LEGACY_TABLES, LEGACY_COLUMNS)
    assert ddl is not None
    assert [s for s in ddl if s.startswith("ALTER")] == [stmt for _, _, stmt in BASELINE_COLUMNS]
    assert ddl[-len(BASELINE_INDEXES) :] == list(BASELINE_INDEXES)


def test_partially_upgraded_database_only_adds_missing_columns():
    cols = {"studies": {"id", "name", "vendor", "provenance"}, "epmaps": {"id", "act_bip"}}
    ddl = legacy_statements(LEGACY_TABLES, cols)
    assert ddl is not None
    assert [s for s in ddl if s.startswith("ALTER")] == [
        "ALTER TABLE epmaps ADD COLUMN scalar_fields JSONB"
    ]


def test_baseline_columns_match_the_initial_revision():
    """The columns listed here must exist in the baseline revision's tables."""
    import importlib.util
    from pathlib import Path

    path = next(
        Path(__file__)
        .resolve()
        .parents[1]
        .glob("src/pulse_ep/migrations/versions/0e7e3563b7fb_*.py")
    )
    source = path.read_text()
    for table, col, _ in BASELINE_COLUMNS:
        assert f"op.create_table('{table}'" in source
        assert f"sa.Column('{col}'" in source
    spec = importlib.util.spec_from_file_location("baseline", path)
    assert spec is not None


def test_revision_from_objects_legacy_is_baseline():
    assert revision_present(LEGACY_TABLES, LEGACY_COLUMNS) == BASELINE_REVISION


def test_revision_from_objects_full_create_all_is_head():
    tables = LEGACY_TABLES | {"waveforms", "measurement_points", "placed_points", "import_jobs"}
    cols = {
        "waveforms": {"id", "point_source_id", "units"},
        "measurement_points": {"id", "tags", "annotations"},
    }
    assert revision_present(tables, cols) == REVISION_MARKERS[-1][0]


def test_revision_from_objects_stops_at_first_gap():
    tables = LEGACY_TABLES | {"waveforms", "measurement_points", "placed_points", "import_jobs"}
    cols = {"waveforms": {"id", "point_source_id"}, "measurement_points": {"id"}}  # no tags yet
    assert revision_present(tables, cols) == "b4f1a7c2d9e3"


def test_revision_from_objects_empty_database():
    assert revision_present(set(), {}) is None


def test_markers_name_real_revisions():
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "src/pulse_ep/migrations/versions"
    on_disk = {p.name.split("_")[0] for p in versions.glob("*.py")}
    assert {rev for rev, _, _ in REVISION_MARKERS} == on_disk


def test_init_db_stamps_and_upgrades(monkeypatch):
    """init_db: create_all + adoption when unstamped, upgrade otherwise; never create_all on a stamped DB."""
    import contextlib
    from types import SimpleNamespace

    import sqlalchemy as sa

    import pulse_ep.cli.migrate as migrate
    import pulse_ep.core.database as db

    calls: list[str] = []
    engine = SimpleNamespace(url=sa.engine.make_url("postgresql://u:p@h/d"))
    monkeypatch.setattr(db.Base.metadata, "create_all", lambda e: calls.append("create_all"))
    monkeypatch.setattr(
        migrate, "adopt_legacy_database", lambda cfg, url: calls.append("adopt") or "rev"
    )
    monkeypatch.setattr("alembic.command.upgrade", lambda cfg, rev: calls.append(f"upgrade:{rev}"))
    monkeypatch.setattr(db, "get_db_session", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(db, "seed_attribute_metadata", lambda s: calls.append("seed"))

    tables = {"value": []}
    monkeypatch.setattr(
        sa, "inspect", lambda e: SimpleNamespace(get_table_names=lambda: tables["value"])
    )

    db.init_db(engine)
    assert calls == ["create_all", "adopt", "upgrade:head", "seed"]

    calls.clear()
    tables["value"] = ["alembic_version", "epmaps"]
    db.init_db(engine)
    assert calls == ["upgrade:head", "seed"]
