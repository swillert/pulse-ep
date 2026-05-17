"""Shared fixtures for the pulse-ep test suite."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def synthetic_atrium_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Small ellipsoidal mesh + Gaussian score field — array form.

    Matches what the importer would yield, but built from pure NumPy so
    no CARTO files are involved.
    """
    from pulse_ep.examples.demo_synthetic import (
        gaussian_score_field,
        make_synthetic_atrium,
    )

    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    return vertices, triangles, scores


@pytest.fixture
def sqlite_engine_and_session():
    """An in-memory SQLite engine with all pulse-ep ORM tables created.

    Yields ``(engine, sessionmaker)`` so tests can open their own
    sessions. JSONB columns in the ORM are not supported by SQLite —
    we skip the ORM smoke test on that backend and verify table
    creation only.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from pulse_ep import Base

    engine = create_engine("sqlite:///:memory:")
    # NOTE: a subset of pulse-ep models use PostgreSQL-specific types
    # (JSONB, ARRAY). The SQLite test here covers the schema-creation
    # path for the portable subset only — full ORM round-trip tests
    # require Postgres and are gated on CI service availability.
    yield engine, sessionmaker(bind=engine)
    engine.dispose()
