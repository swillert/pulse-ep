import configparser
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pulse_ep.core.models import AttributeMetadata, Base


@contextmanager
def get_db_session():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
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


def create_db_engine():
    config = configparser.ConfigParser()
    config.read("config.ini")
    db = config["database"]
    uri = f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['dbname']}"
    engine = create_engine(
        uri,
        pool_pre_ping=True,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )
    return engine


def init_db(engine=None):
    """Create all tables and seed metadata. Safe to call multiple times."""
    if engine is None:
        engine = create_db_engine()
    Base.metadata.create_all(engine)
    with get_db_session() as session:
        seed_attribute_metadata(session)


# Module-level engine and session factory
engine = create_db_engine()
Session = sessionmaker(engine)

# Auto-init: create tables if they don't exist (safe for normal server startup)
try:
    init_db(engine)
except Exception:
    # Silently skip if DB is being rebuilt (tables dropped but not yet recreated)
    pass
