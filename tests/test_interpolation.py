"""Computing a surface field from the measurement points, instead of masking.

``EPMap.interpolate_scalar_values`` only ever masked the vendor's own field.
These tests pin the two computed alternatives — and the cases that make them
worth having: a surface that folds back on itself, and an activation map whose
late meets its early.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.interpolation import (
    default_sigma,
    gaussian_interpolate,
    heat_interpolate,
)
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.scalar_field import ACTIVATION_TIME, VOLTAGE_BIPOLAR


def _grid_mesh(nx=21, ny=11, spacing=1.0):
    """A flat triangulated sheet in the z=0 plane."""
    xs = np.arange(nx) * spacing
    ys = np.arange(ny) * spacing
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    vertices = np.column_stack([X.ravel(), Y.ravel(), np.zeros(X.size)])
    tris = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a, b, c, d = (
                i * ny + j,
                (i + 1) * ny + j,
                (i + 1) * ny + j + 1,
                i * ny + j + 1,
            )
            tris += [[a, b, c], [a, c, d]]
    return vertices, np.array(tris)


def _folded_mesh(n=21, ny=5, spacing=1.0, gap=0.4):
    """A sheet folded back on itself: a hairpin with a ``gap`` mm slit.

    Vertex ``(i, j)`` for ``i < n`` is on the near leaf, ``i >= n`` on the far
    one. The two leaves are ``gap`` apart in space and up to ``2 * n * spacing``
    apart *along the surface* — the geometry every intracardiac map has at a
    ridge or a thin wall, and the one case where straight-line distance is a
    lie.
    """
    rows = []
    for i in range(n):  # out along the near leaf
        rows.append((i * spacing, 0.0))
    for i in range(n - 1, -1, -1):  # and back along the far one
        rows.append((i * spacing, gap))
    vertices, tris = [], []
    for x, z in rows:
        for j in range(ny):
            vertices.append([x, j * spacing, z])
    for r in range(len(rows) - 1):
        for j in range(ny - 1):
            a, b = r * ny + j, (r + 1) * ny + j
            tris += [[a, b, b + 1], [a, b + 1, a + 1]]
    return np.array(vertices, dtype=float), np.array(tris), len(rows)


def test_gaussian_reproduces_a_linear_field():
    """Interpolating a plane through scattered samples of it returns the plane."""
    vertices, _ = _grid_mesh()
    rng = np.random.default_rng(0)
    sources = np.column_stack(
        [rng.uniform(0, 20, 80), rng.uniform(0, 10, 80), np.zeros(80)],
    )
    values = 2.0 * sources[:, 0] + 3.0

    out = gaussian_interpolate(vertices, sources, values, sigma=2.0)
    expected = 2.0 * vertices[:, 0] + 3.0
    # A kernel average of a linear field is the field, up to edge effects and
    # the bias a weighted mean carries wherever sampling is uneven — a few
    # percent of the field's 40-unit range.
    interior = (vertices[:, 0] > 3) & (vertices[:, 0] < 17)
    assert np.abs(out[interior] - expected[interior]).max() < 3.0


def test_the_confidence_mask_survives_computing():
    """Recomputing must not start inventing values where nothing was measured."""
    vertices, _ = _grid_mesh()
    sources = np.array([[0.0, 5.0, 0.0], [1.0, 5.0, 0.0]])
    out = gaussian_interpolate(vertices, sources, np.array([1.0, 1.0]), distance_threshold=3.0)

    far = vertices[:, 0] > 10
    assert np.isnan(out[far]).all()
    assert np.isfinite(out[vertices[:, 0] < 1]).any()


def test_points_without_a_value_do_not_count_as_zero():
    vertices, _ = _grid_mesh()
    sources = np.array([[5.0, 5.0, 0.0], [5.5, 5.0, 0.0]])
    values = np.array([10.0, np.nan])  # an unannotated point
    out = gaussian_interpolate(vertices, sources, values, sigma=1.0)
    assert np.nanmax(out) == pytest.approx(10.0)


def test_geodesic_does_not_leak_across_a_fold():
    """The whole reason for a surface metric: the far leaf is not 0.4 mm away."""
    vertices, triangles, n_rows = _folded_mesh()
    ny = len(vertices) // n_rows

    # one measurement at the open end of the near leaf
    source_vertex = 0
    values = np.array([100.0])

    near_tip = 0
    far_tip = (n_rows - 1) * ny  # same x, other leaf: 0.4 mm away, ~40 mm along tissue

    geodesic = heat_interpolate(
        vertices, triangles, [source_vertex], values, sigma=3.0, distance_threshold=10.0
    )
    euclidean = gaussian_interpolate(
        vertices, vertices[[source_vertex]], values, sigma=3.0, distance_threshold=10.0
    )

    assert geodesic[near_tip] == pytest.approx(100.0, rel=0.05)
    assert euclidean[near_tip] == pytest.approx(100.0, rel=0.05)

    # straight-line weighting puts the full value on the far leaf …
    assert euclidean[far_tip] == pytest.approx(100.0, rel=0.05)
    # … while along the surface, nothing measured is anywhere near it
    assert np.isnan(geodesic[far_tip])


def test_geodesic_reproduces_a_field_measured_densely():
    vertices, triangles = _grid_mesh(nx=15, ny=15)
    idx = np.arange(0, len(vertices), 7)
    values = 2.0 * vertices[idx, 0] + 5.0

    out = heat_interpolate(vertices, triangles, idx, values, sigma=2.0)
    expected = 2.0 * vertices[:, 0] + 5.0
    interior = (vertices[:, 0] > 3) & (vertices[:, 0] < 11)
    assert np.abs(out[interior] - expected[interior]).max() < 2.0


def test_cyclic_interpolation_joins_late_to_early():
    """5 ms and 295 ms of a 300 ms cycle are neighbours, not 150 ms apart."""
    vertices, _ = _grid_mesh(nx=3, ny=3, spacing=1.0)
    sources = np.array([[0.0, 1.0, 0.0], [2.0, 1.0, 0.0]])
    values = np.array([5.0, 295.0])
    middle = np.array([[1.0, 1.0, 0.0]])

    linear = gaussian_interpolate(middle, sources, values, sigma=2.0)[0]
    cyclic = gaussian_interpolate(middle, sources, values, sigma=2.0, cycle_length=300.0)[0]

    assert linear == pytest.approx(150.0, abs=1.0)  # straight through the wavefront
    # on the circle the two are 10 ms apart, so their mean sits at the wrap
    assert min(abs(cyclic - 300.0), abs(cyclic - 0.0), abs(cyclic - 5.0)) < 6.0


def test_cycle_length_zero_is_inferred_from_the_data():
    vertices, _ = _grid_mesh(nx=3, ny=3)
    sources = np.array([[0.0, 1.0, 0.0], [2.0, 1.0, 0.0]])
    values = np.array([0.0, 290.0])
    out = gaussian_interpolate(vertices, sources, values, sigma=2.0, cycle_length=0)
    assert np.isfinite(out).all()
    assert out.min() >= 0.0 and out.max() <= 290.0


def test_default_sigma_follows_the_point_spacing():
    points = np.column_stack([np.arange(10) * 2.5, np.zeros(10), np.zeros(10)])
    assert default_sigma(points) == pytest.approx(2.5)


# --- the EPMap surface ------------------------------------------------------


def _map_with_points(n=40):
    vertices, triangles = _grid_mesh(nx=15, ny=9)
    epmap = EPMap(map_name="m", study_name="s", vertices=vertices, triangles=triangles)
    rng = np.random.default_rng(1)
    xs = rng.uniform(0, 14, n)
    ys = rng.uniform(0, 8, n)
    epmap.measurement_points = [
        MeasurementPoint(position=np.array([x, y, 0.0])) for x, y in zip(xs, ys, strict=True)
    ]
    for point in epmap.measurement_points:
        point.add("activation_time", 2.0 * point.position[0], ACTIVATION_TIME)
    # a vendor field that is deliberately wrong, so a computed result cannot
    # accidentally be the masked one
    epmap.register_scalar("activation_time", np.zeros(len(vertices)), kind=ACTIVATION_TIME)
    return epmap


def test_epmap_can_compute_instead_of_mask():
    epmap = _map_with_points()
    epmap.generate_anatomical_pv_mesh(simplify=False)

    _mesh, masked = epmap.interpolate_scalar_values(
        epmap.get_scalar("activation_time"), distance_threshold=50.0
    )
    _mesh, computed = epmap.interpolate_scalar_values(
        epmap.get_scalar("activation_time"), method="gaussian", sigma=2.0
    )

    assert np.nanmax(np.abs(masked)) == 0.0  # the vendor's (empty) field
    assert np.nanmax(computed) > 10.0  # our own, from the points
    x = epmap.pv_mesh.points[:, 0]
    interior = np.isfinite(computed) & (x > 3) & (x < 11)
    assert np.corrcoef(computed[interior], 2.0 * x[interior])[0, 1] > 0.99


def test_epmap_geodesic_runs_on_the_display_mesh():
    epmap = _map_with_points()
    epmap.generate_anatomical_pv_mesh(simplify=False)
    _mesh, computed = epmap.interpolate_scalar_values(
        epmap.get_scalar("activation_time"), method="geodesic", sigma=2.0
    )
    x = epmap.pv_mesh.points[:, 0]
    interior = np.isfinite(computed) & (x > 3) & (x < 11)
    assert interior.sum() > 10
    assert np.corrcoef(computed[interior], 2.0 * x[interior])[0, 1] > 0.98


def test_computing_a_quantity_the_points_do_not_carry_is_an_error():
    """Better a clear refusal than a plausible field built from nothing."""
    epmap = _map_with_points()
    epmap.register_scalar("voltage_bipolar", np.ones(len(epmap.vertices)), kind=VOLTAGE_BIPOLAR)
    epmap.generate_anatomical_pv_mesh(simplify=False)

    with pytest.raises(ValueError, match="carry no such quantity"):
        epmap.interpolate_scalar_values(
            epmap.get_scalar("voltage_bipolar"),
            scalar_name="voltage_bipolar",
            method="gaussian",
        )


def test_an_unknown_method_is_refused():
    epmap = _map_with_points()
    epmap.generate_anatomical_pv_mesh(simplify=False)
    with pytest.raises(ValueError, match="unknown interpolation method"):
        epmap.interpolate_scalar_values(epmap.get_scalar("activation_time"), method="rbf")
