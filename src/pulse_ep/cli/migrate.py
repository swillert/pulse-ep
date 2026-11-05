"""Apply the packaged database migrations.

``alembic upgrade head`` only works from a source checkout: ``alembic.ini``
and the migration scripts are not on an installed system's path. This command
runs the same migrations against the configured database from anywhere, so a
``pip install``ed deployment can keep its schema in step with a release —
which the project's additive-migration promise depends on.

Databases without an ``alembic_version`` table are adopted first. Two kinds
exist: databases created by ``Base.metadata.create_all()`` up to release 0.5
(they lack the three columns the baseline revision added; these are created
and the baseline is stamped), and databases that ``init_db()`` created or
extended with ``create_all()`` on a later release (their tables already match
some revision; that revision is found from the objects present and stamped).
The remaining revisions then apply as usual. Without this, ``alembic upgrade
head`` would try to create the existing tables and stop at "relation already
exists".
"""

from __future__ import annotations

import argparse
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

#: first revision; the schema create_all() produced up to 0.5 plus the columns below
BASELINE_REVISION = "0e7e3563b7fb"
#: columns of the baseline revision that a create_all()-era database lacks
BASELINE_COLUMNS = (
    ("studies", "vendor", "ALTER TABLE studies ADD COLUMN vendor VARCHAR"),
    ("studies", "provenance", "ALTER TABLE studies ADD COLUMN provenance JSONB"),
    ("epmaps", "scalar_fields", "ALTER TABLE epmaps ADD COLUMN scalar_fields JSONB"),
)
BASELINE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_studies_id ON studies (id)",
    "CREATE INDEX IF NOT EXISTS ix_studies_vendor ON studies (vendor)",
)
#: the revision chain and, for each revision after the baseline, the object it adds:
#: (revision, table, column or None). A database holding the objects of revisions
#: 1..k but not k+1 is stamped at revision k.
REVISION_MARKERS = (
    (BASELINE_REVISION, "epmaps", None),
    ("61863fd599e4", "waveforms", None),
    ("cc7318c9c1de", "measurement_points", None),
    ("6f7abb350e3b", "placed_points", None),
    ("0c2994f1da5b", "import_jobs", None),
    ("b4f1a7c2d9e3", "waveforms", "point_source_id"),
    ("d7e2c4a9f1b6", "measurement_points", "tags"),
    ("f3a8b5c6d201", "measurement_points", "annotations"),
    ("a1c3e5f70b92", "waveforms", "units"),
)


def revision_present(tables: set[str], columns: dict[str, set[str]]) -> str | None:
    """The last revision whose objects (and those of all earlier ones) exist, or ``None``."""
    found = None
    for rev, table, col in REVISION_MARKERS:
        if table not in tables or (col is not None and col not in columns.get(table, set())):
            break
        found = rev
    return found


def legacy_statements(tables: set[str], columns: dict[str, set[str]]) -> list[str] | None:
    """DDL that brings a pre-migration database to the baseline revision.

    ``tables`` are the database's table names, ``columns`` the column names of
    the tables in :data:`BASELINE_COLUMNS`. Returns ``None`` when the database
    is not a legacy one (fresh and empty, or already under Alembic) and the
    list of statements otherwise (possibly empty, when only the stamp is
    missing).
    """
    if "alembic_version" in tables or "epmaps" not in tables:
        return None
    ddl = [stmt for table, col, stmt in BASELINE_COLUMNS if col not in columns.get(table, set())]
    return ddl + list(BASELINE_INDEXES)


def adopt_legacy_database(cfg, url: str) -> str | None:
    """Stamp a database without ``alembic_version`` at the revision its schema matches.

    Returns the stamped revision, or ``None`` when nothing was to do (fresh and
    empty database, or already under Alembic). Idempotent: a second run finds
    ``alembic_version`` and returns.
    """
    import sqlalchemy as sa
    from alembic import command

    engine = sa.create_engine(url)
    try:
        insp = sa.inspect(engine)
        tables = set(insp.get_table_names())
        watched = {t for t, _, _ in BASELINE_COLUMNS} | {t for _, t, _ in REVISION_MARKERS}
        columns = {t: {c["name"] for c in insp.get_columns(t)} for t in watched if t in tables}
        ddl = legacy_statements(tables, columns)
        if ddl is None:
            return None
        with engine.begin() as conn:
            for stmt in ddl:
                conn.execute(sa.text(stmt))
    finally:
        engine.dispose()
    rev = revision_present(tables, columns) or BASELINE_REVISION
    command.stamp(cfg, rev)
    print(
        f"database without alembic_version adopted: stamped at {rev} ({len(ddl)} statements applied)"
    )
    return rev


def _alembic_config(url: str):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    # Alembic's ConfigParser interprets %, including URL-encoded passwords.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-migrate",
        description="Bring the configured database up to the current schema.",
    )
    p.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: %(default)s — the newest).",
    )
    p.add_argument(
        "--current",
        action="store_true",
        help="Report the database's current revision and exit.",
    )
    p.add_argument(
        "--sql",
        action="store_true",
        help="Print the SQL instead of executing it (offline mode).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from alembic import command

    from pulse_ep.core.config import get_settings

    url = get_settings().resolved_database_url
    if not url:
        raise SystemExit("No database configured. Set PULSE_EP_DATABASE_URL (see .env.example).")

    cfg = _alembic_config(url)
    if args.current:
        command.current(cfg, verbose=True)
    else:
        if not args.sql:
            adopt_legacy_database(cfg, url)
        command.upgrade(cfg, args.revision, sql=args.sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
