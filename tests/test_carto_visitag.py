"""VisiTag ablation sites.

The parser has been confirmed by a co-author against a real VisiTag export
(September 2026). These fixtures still encode the *documented* layout rather
than that export's header, because a real one is patient data and cannot be
committed here. So they pin the properties that make the parser safe on a
column set it has not seen — name-driven mapping, no positional guessing, and
a refusal to invent points when the columns are unrecognisable — rather than
one CARTO version's spelling.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.carto import parse_carto_visitag_sites
from pulse_ep.core.placed_point import ABLATION

# Assumed layout: tab-separated, one header row, one row per site.
_SITES = (
    "Session\tSiteIndex\tX\tY\tZ\tDurationTime\tAverageForce\tFTI\tMaxTemperature\t"
    "MaxPower\tBaseImpedance\tImpedanceDrop\tRFIndex\n"
    "1\t7\t-39.15\t7.19\t98.08\t22.5\t12.3\t276.8\t41.2\t35.0\t112.4\t9.8\t512.0\n"
    "1\t8\t-41.02\t8.44\t97.10\t18.0\t10.1\t181.8\t40.1\t35.0\t111.9\t7.2\t470.5\n"
)


def test_sites_become_ablation_placed_points():
    pts = parse_carto_visitag_sites(_SITES)
    assert len(pts) == 2
    assert all(p.type == ABLATION for p in pts)
    np.testing.assert_allclose(pts[0].position, [-39.15, 7.19, 98.08])


def test_rf_parameters_land_under_stable_names():
    p = parse_carto_visitag_sites(_SITES)[0]
    assert p.attributes["duration_s"] == 22.5
    assert p.attributes["average_force_g"] == 12.3
    assert p.attributes["force_time_integral"] == 276.8
    assert p.attributes["impedance_drop_ohm"] == 9.8
    assert p.attributes["rf_index"] == 512.0
    assert p.source_id == "7"


def test_columns_are_matched_by_name_not_position():
    """The property that makes an unverified parser safe: reordering the
    columns must not reassign values to the wrong quantity."""
    reordered = (
        "RFIndex\tZ\tAverageForce\tY\tSiteIndex\tX\tDurationTime\n"
        "512.0\t98.08\t12.3\t7.19\t7\t-39.15\t22.5\n"
    )
    p = parse_carto_visitag_sites(reordered)[0]
    np.testing.assert_allclose(p.position, [-39.15, 7.19, 98.08])
    assert p.attributes["average_force_g"] == 12.3
    assert p.attributes["rf_index"] == 512.0


def test_column_names_are_matched_case_and_separator_insensitively():
    variant = "Site Index\tx\ty\tz\tAverage Force\n7\t1\t2\t3\t9.5\n"
    p = parse_carto_visitag_sites(variant)[0]
    np.testing.assert_allclose(p.position, [1, 2, 3])
    assert p.attributes["average_force_g"] == 9.5


def test_an_unknown_column_is_kept_under_its_own_name():
    extra = "X\tY\tZ\tSomeNewMetric\n1\t2\t3\t42\n"
    p = parse_carto_visitag_sites(extra)[0]
    assert p.attributes["SomeNewMetric"] == 42.0


def test_no_coordinates_means_no_points_rather_than_guesses():
    """A table whose columns are not recognisable must yield nothing —
    inventing ablation sites is the failure mode worth avoiding."""
    assert parse_carto_visitag_sites("A\tB\tC\n1\t2\t3\n") == []
    assert parse_carto_visitag_sites("") == []


def test_unparseable_rows_are_skipped_not_zeroed():
    broken = "X\tY\tZ\n1\t2\t3\nnan-ish\tb\tc\n4\t5\t6\n"
    pts = parse_carto_visitag_sites(broken)
    assert len(pts) == 2
    np.testing.assert_allclose(pts[1].position, [4, 5, 6])


def test_whitespace_separated_variant_is_tolerated():
    spaced = "X   Y   Z   AverageForce\n1   2   3   7.5\n"
    p = parse_carto_visitag_sites(spaced)[0]
    np.testing.assert_allclose(p.position, [1, 2, 3])
    assert p.attributes["average_force_g"] == 7.5
