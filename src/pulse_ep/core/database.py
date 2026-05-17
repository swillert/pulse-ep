"""Database engine & session factory for pulse-ep.

Configuration is resolved (in order) from:

1. ``PULSE_EP_DATABASE_URL`` environment variable — a full SQLAlchemy URL.
2. ``config.ini`` (path overridable via ``PULSE_EP_CONFIG``) with a
   ``[database]`` section containing ``user``, ``password``, ``host``,
   ``port``, ``dbname``.

Engine and session factory are **lazily created** on first
:func:`get_db_session` call, so importing :mod:`pulse_ep` in an
environment without any DB configuration (CI runners, docs builders,
fresh ``pip install`` smoke tests) does not fail.
"""

from __future__ import annotations

import configparser
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pulse_ep.core.models import AttributeMetadata, Base

_engine = None
_Session: sessionmaker | None = None


def _resolve_database_url() -> str | None:
    """Resolve the SQLAlchemy URL or return ``None`` if no config is present."""
    env_url = os.environ.get("PULSE_EP_DATABASE_URL")
    if env_url:
        return env_url

    config_path = os.environ.get("PULSE_EP_CONFIG", "config.ini")
    if not os.path.exists(config_path):
        return None

    config = configparser.ConfigParser()
    config.read(config_path)
    if "database" not in config:
        return None

    db = config["database"]
    required = ("user", "password", "host", "port", "dbname")
    if not all(k in db for k in required):
        return None
    return (
        f"postgresql://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['dbname']}"
    )


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
    """Create all tables and seed metadata. Safe to call multiple times.

    Server entry points (e.g. ``pulse_ep.server.app``) should call this
    once at startup. It is **not** invoked automatically anymore to keep
    package imports side-effect-free.
    """
    if engine is None:
        engine = create_db_engine()
    Base.metadata.create_all(engine)
    with get_db_session() as session:
        seed_attribute_metadata(session)
