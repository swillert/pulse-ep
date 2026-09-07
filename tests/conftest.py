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
