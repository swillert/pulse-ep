"""Apply the packaged database migrations.

``alembic upgrade head`` only works from a source checkout: ``alembic.ini``
and the migration scripts are not on an installed system's path. This command
runs the same migrations against the configured database from anywhere, so a
``pip install``ed deployment can keep its schema in step with a release —
which the project's additive-migration promise depends on.
"""

from __future__ import annotations

import argparse
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _alembic_config(url: str):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
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
        command.upgrade(cfg, args.revision, sql=args.sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
