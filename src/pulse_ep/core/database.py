"""Database engine & session factory for pulse-ep.

Database configuration is resolved via :mod:`pulse_ep.core.config`. The
URL can come from any of these sources (highest priority first):

1. ``PULSE_EP_DATABASE_URL`` environment variable (full SQLAlchemy URL).
2. ``PULSE_EP_DATABASE_{USER,PASSWORD,HOST,PORT,NAME}`` components.
3. A ``.env`` file in the working directory.
4. Legacy ``config.ini`` with a ``[database]`` section.

Engine and session factory are **lazily created** on first
:func:`get_db_session` call, so importing :mod:`pulse_ep` in an
environment without any DB configuration (CI runners, docs builders,
fresh ``pip install`` smoke tests) does not fail.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pulse_ep.core.config import get_settings
from pulse_ep.core.models import AttributeMetadata, Base

_engine = None
_Session: sessionmaker | None = None


def _resolve_database_url() -> str | None:
    """Resolve the SQLAlchemy URL or return ``None`` if no config is present.

    Delegates to :func:`pulse_ep.core.config.get_settings`, so the
    resolution order is whatever the :class:`Settings` model defines.
    Kept as a module-level helper for backwards compatibility with code
    that imported it directly (and for ease of monkey-patching in tests).
    """
    return get_settings().resolved_database_url


def create_db_engine(url: str | None = None):
    """Create a SQLAlchemy engine.

    Raises :class:`RuntimeError` when no URL is configured — call sites
    that need a DB should expect this and surface it clearly.
    """
    if url is None:
        url = _resolve_database_url()
    if url is None:
        raise RuntimeError(
            "No pulse-ep database configuration found. "
            "Set PULSE_EP_DATABASE_URL or provide a config.ini with a [database] section."
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )


def _get_session_factory() -> sessionmaker:
    """Lazy-initialize the module-level engine + session factory."""
    global _engine, _Session
    if _Session is None:
        _engine = create_db_engine()
        _Session = sessionmaker(_engine)
    return _Session


@contextmanager
def get_db_session():
    """Provide a transactional scope around a series of operations."""
    Session = _get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def seed_attribute_metadata(session):
    """Seed initial values into the attribute_metadata table."""
    default_metadata = [
        {"name": "type", "data_type": "string", "default_value": ""},
        {"name": "atrium", "data_type": "string", "default_value": ""},
        {"name": "part", "data_type": "string", "default_value": ""},
        {"name": "pacemap", "data_type": "boolean", "default_value": False},
        {"name": "imported by", "data_type": "String", "default_value": "unknown"},
        {"name": "importer", "data_type": "String", "default_value": "unknown"},
        {"name": "reference_electrodes", "data_type": "int", "default_value": 0},
    ]

    if session.query(AttributeMetadata).count() > 0:
        return

    for meta in default_metadata:
        session.add(AttributeMetadata(**meta))
    session.commit()
    print("AttributeMetadata table seeded successfully.")


def init_db(engine=None):
    """Create a missing schema, bring an existing one up to date, seed metadata.

    Server entry points (e.g. ``pulse_ep.server.app``) call this once at
    startup; it is idempotent. Three situations:

    - fresh database: ``create_all()`` builds the current schema and the head
      revision is stamped, so later ``pulse-ep-migrate`` runs start from there
      instead of trying to create the tables again;
    - database without ``alembic_version`` (created by ``create_all()`` on an
      earlier release): missing tables are created, the columns the baseline
      revision added are completed and the revision the schema matches is
      stamped (:func:`pulse_ep.cli.migrate.adopt_legacy_database`);
    - database under Alembic: pending migrations are applied; ``create_all()``
      is not used, so the schema never drifts ahead of its stamp.
    """
    import sqlalchemy as sa
    from alembic import command

    from pulse_ep.cli.migrate import _alembic_config, adopt_legacy_database

    if engine is None:
        engine = create_db_engine()
    url = engine.url.render_as_string(hide_password=False)
    cfg = _alembic_config(url)
    if "alembic_version" not in sa.inspect(engine).get_table_names():
        Base.metadata.create_all(engine)
        adopt_legacy_database(cfg, url)
    command.upgrade(cfg, "head")
    with get_db_session() as session:
        seed_attribute_metadata(session)
