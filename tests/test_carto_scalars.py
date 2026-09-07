"""CARTO primary-scalar auto-classification (``classify_primary_scalar``).

Non-positive values in [-100, 0] suggest a pace-mapping correlation;
values outside that range remain activation times. Sentinels become NaN.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.carto import CARTO_SENTINEL, classify_primary_scalar
from pulse_ep.core.scalar_field import ACTIVATION_TIME, PACEMAP_SCORE


def test_all_negative_is_pacemapping_and_flipped() -> None:
    kind, values = classify_primary_scalar(np.array([-90.0, -50.0, -100.0]))
    assert kind == PACEMAP_SCORE
    np.testing.assert_array_equal(values, np.array([90.0, 50.0, 100.0]))


def test_positive_is_activation_time_unchanged() -> None:
    kind, values = classify_primary_scalar(np.array([10.0, 40.0, 250.0]))
    assert kind == ACTIVATION_TIME
    np.testing.assert_array_equal(values, np.array([10.0, 40.0, 250.0]))


def test_negative_activation_beyond_percentage_range_keeps_its_sign() -> None:
    original = np.array([-154.67317, -105.0, -40.0])
    kind, values = classify_primary_scalar(original)
    assert kind == ACTIVATION_TIME
    np.testing.assert_array_equal(values, original)


def test_zero_score_and_negative_sentinel_do_not_change_pace_classification() -> None:
    kind, values = classify_primary_scalar(np.array([-96.0, 0.0, -CARTO_SENTINEL]))
    assert kind == PACEMAP_SCORE
    np.testing.assert_allclose(values, [96, 0, np.nan])


def test_point_only_negative_lat_uses_the_same_range_check() -> None:
    from pulse_ep.core.importers.carto import decode_point_annotations

    kind, values = decode_point_annotations(
        [
            {"reference_annotation": 1250, "map_annotation": 1095},
            {"reference_annotation": 1250, "map_annotation": 1210},
        ]
    )
    assert kind == ACTIVATION_TIME
    assert values == [-155, -40]


def test_mixed_sign_positive_max_is_activation() -> None:
    # A signed activation map (negatives present but max positive) must NOT
    # be misread as pace-mapping.
    kind, values = classify_primary_scalar(np.array([-50.0, 20.0, 250.0]))
    assert kind == ACTIVATION_TIME
    np.testing.assert_array_equal(values, np.array([-50.0, 20.0, 250.0]))


def test_sentinel_masked_to_nan() -> None:
    kind, values = classify_primary_scalar(np.array([12.0, CARTO_SENTINEL, 40.0]))
    assert kind == ACTIVATION_TIME
    assert np.isnan(values[1])
    np.testing.assert_array_equal(values[[0, 2]], np.array([12.0, 40.0]))


def test_sentinel_only_after_masking_still_classifies() -> None:
    # all-sentinel → all NaN → no finite values → defaults to activation_time
    kind, values = classify_primary_scalar(np.array([CARTO_SENTINEL, CARTO_SENTINEL]))
    assert kind == ACTIVATION_TIME
    assert np.all(np.isnan(values))
