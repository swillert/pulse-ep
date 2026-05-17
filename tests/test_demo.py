"""End-to-end smoke test of the pulse-ep-demo entry point.

Runs the synthetic walkthrough at low resolution and checks that:
  - it exits cleanly,
  - it prints the area-breakdown table,
  - the EPMap it constructs has the expected shape.
"""

from __future__ import annotations

import numpy as np

from pulse_ep import EPMap
from pulse_ep.examples.demo_synthetic import (
    area_breakdown,
    gaussian_score_field,
    main,
    make_synthetic_atrium,
    triangle_areas,
)


def test_make_synthetic_atrium_shape() -> None:
    vertices, triangles = make_synthetic_atrium(resolution=16)
    assert vertices.ndim == 2 and vertices.shape[1] == 3
    assert triangles.ndim == 2 and triangles.shape[1] == 3
    assert triangles.dtype == np.int64
    # Indices stay in range
    assert triangles.max() < len(vertices)


def test_gaussian_field_peak_is_at_origin() -> None:
    vertices, _ = make_synthetic_atrium(resolution=16)
    scores, origin_idx = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    assert scores[origin_idx] == scores.max()
    assert 0.0 <= scores.min() <= scores.max() <= 100.0


def test_triangle_areas_positive() -> None:
    vertices, triangles = make_synthetic_atrium(resolution=12)
    a = triangle_areas(vertices, triangles)
    assert (a > 0).all()


def test_area_breakdown_sums_to_total() -> None:
    vertices, triangles = make_synthetic_atrium(resolution=12)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    a = triangle_areas(vertices, triangles)
    bins = np.array([0, 20, 40, 60, 80, 100, 101], dtype=float)
    breakdown = area_breakdown(triangles, a, scores, bins)
    # Bins cover the full score range [0, 100]; every triangle falls into
    # exactly one interval, so the per-interval areas must sum to total.
    assert np.isclose(sum(breakdown.values()), a.sum())


def test_epmap_can_wrap_synthetic_data() -> None:
    vertices, triangles = make_synthetic_atrium(resolution=12)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    epmap = EPMap(
        map_name="t",
        study_name="t",
        triangles=triangles,
        vertices=vertices,
        act_bip=np.column_stack([scores, np.zeros_like(scores)]),
    )
    assert epmap.map_name == "t"
    assert len(epmap.vertices) == len(vertices)
    assert epmap.act_bip.shape == (len(vertices), 2)


def test_main_exits_zero(capsys) -> None:
    rc = main(["--resolution", "12", "--sigma", "6.0"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "synthetic atrium" in captured
    assert "Area by score interval" in captured
