"""The /epmaps/<id>/scalars payload must carry each quantity's range.

Without it a client has to guess: the shipped R and MATLAB examples assumed
pace-mapping percentages and reported 0.000 cm² of area for every bipolar
voltage map, which reads as a result rather than as a mismatch.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.server.app import _scalar_range


def test_range_of_a_plain_field():
    out = _scalar_range([0.5, 1.5, 2.5])
    assert out == {"min": 0.5, "max": 2.5, "n_valid": 3}


def test_nan_marks_absent_measurements_and_is_ignored():
    out = _scalar_range([np.nan, 1.0, np.nan, 3.0])
    assert out["min"] == 1.0
    assert out["max"] == 3.0
    assert out["n_valid"] == 2


def test_all_nan_reports_nulls_rather_than_failing():
    out = _scalar_range([np.nan, np.nan])
    assert out == {"min": None, "max": None, "n_valid": 0}


def test_missing_field_is_not_an_error():
    assert _scalar_range(None) == {"min": None, "max": None, "n_valid": 0}


def test_infinities_are_not_treated_as_data():
    """An export sentinel that decoded to inf must not become the range."""
    out = _scalar_range([1.0, np.inf, 2.0, -np.inf])
    assert (out["min"], out["max"], out["n_valid"]) == (1.0, 2.0, 2)
