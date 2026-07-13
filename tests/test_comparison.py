"""compare_maps: euclidean / geodesic nearest-neighbour delta fields."""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep import EPMap
from pulse_ep.core.comparison import compare_maps
from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR
from pulse_ep.examples.demo_synthetic import make_synthetic_atrium


def _map(resolution, values):
    verts, tris = make_synthetic_atrium(resolution=resolution)
    ep = EPMap(map_name="m", study_name="s", vertices=verts, triangles=tris)
    ep.register_scalar("voltage_bipolar", values(verts), kind=VOLTAGE_BIPOLAR)
    return ep


@pytest.mark.parametrize("metric", ["euclidean", "geodesic"])
def test_identical_maps_zero_delta(metric):
    ep = _map(16, lambda v: v[:, 2])  # scalar = z
    result = compare_maps(ep, ep, "voltage_bipolar", metric=metric)
    assert result.delta.shape == (ep.vertices.shape[0],)
    np.testing.assert_allclose(result.delta, 0.0, atol=1e-9)


@pytest.mark.parametrize("metric", ["euclidean", "geodesic"])
def test_constant_offset_recovered(metric):
    a = _map(16, lambda v: v[:, 2])
    b = _map(16, lambda v: v[:, 2] - 5.0)  # same geometry, b = a - 5
    result = compare_maps(a, b, "voltage_bipolar", metric=metric)
    # mesh coords are float32 (pyvista) → the offset carries ~1e-6 rounding
    np.testing.assert_allclose(result.delta, 5.0, atol=1e-3)  # a - b = +5


def test_different_resolution_is_finite():
    a = _map(20, lambda v: v[:, 2])
    b = _map(12, lambda v: v[:, 2])  # coarser mesh, same field
    result = compare_maps(a, b, "voltage_bipolar", metric="euclidean")
    assert np.isfinite(result.delta).all()
    assert abs(result.stats()["mean"]) < 2.0  # same underlying field → small delta


def test_max_distance_masks_far_correspondences():
    a = _map(16, lambda v: v[:, 2])
    b = _map(16, lambda v: v[:, 2])
    result = compare_maps(a, b, "voltage_bipolar", metric="euclidean", max_distance=1e-6)
    # identical vertices → distance 0, nothing masked
    assert result.n_masked == 0
    # a tiny negative threshold would mask everything
    r2 = compare_maps(a, b, "voltage_bipolar", metric="euclidean", max_distance=-1.0)
    assert r2.n_masked == a.vertices.shape[0]
    assert np.isnan(r2.delta).all()


def test_stats_and_bad_metric():
    a = _map(16, lambda v: v[:, 2])
    r = compare_maps(a, a, "voltage_bipolar")
    s = r.stats()
    assert s["n"] == a.vertices.shape[0] and abs(s["mean"]) < 1e-9
    with pytest.raises(ValueError, match="unknown metric"):
        compare_maps(a, a, "voltage_bipolar", metric="manhattan")


@pytest.mark.parametrize("solver", ["dijkstra", "heat"])
def test_geodesic_solvers_recover_offset(solver):
    a = _map(12, lambda v: v[:, 2])
    b = _map(12, lambda v: v[:, 2] - 5.0)
    r = compare_maps(a, b, "voltage_bipolar", metric="geodesic", geodesic_solver=solver)
    np.testing.assert_allclose(r.delta, 5.0, atol=1e-2)


def test_bad_geodesic_solver():
    a = _map(12, lambda v: v[:, 2])
    with pytest.raises(ValueError, match="unknown geodesic_solver"):
        compare_maps(a, a, "voltage_bipolar", metric="geodesic", geodesic_solver="foo")
