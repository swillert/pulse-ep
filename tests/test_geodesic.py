"""Heat Method geodesic distance — validated against a planar mesh."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.geodesic import heat_geodesic, nearest_source


def _grid(n=21):
    xs = np.linspace(0, 1, n)
    gx, gy = np.meshgrid(xs, xs)
    verts = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(n * n)])
    tris = []
    idx = lambda r, c: r * n + c  # noqa: E731
    for r in range(n - 1):
        for c in range(n - 1):
            tris.append([idx(r, c), idx(r, c + 1), idx(r + 1, c)])
            tris.append([idx(r, c + 1), idx(r + 1, c + 1), idx(r + 1, c)])
    return verts, np.array(tris)


def test_heat_matches_euclidean_on_a_plane():
    verts, tris = _grid(21)
    src = [0]  # corner (0,0)
    d = heat_geodesic(verts, tris, src)
    eucl = np.linalg.norm(verts - verts[0], axis=1)  # true geodesic on a plane
    assert d[0] == 0.0
    far = eucl > 0.1
    rel = np.abs(d[far] - eucl[far]) / eucl[far]
    assert np.median(rel) < 0.05  # a few % — typical Heat Method accuracy
    assert np.max(np.abs(d - eucl)) < 0.1


def test_nearest_source_partitions_by_proximity():
    verts, tris = _grid(11)
    left, right = 0, 10  # two corners of the same row
    d = heat_geodesic(verts, tris, [left, right])
    labels = nearest_source(verts, tris, [left, right], d)
    # a vertex near the left edge should be labelled to the left source
    n = 11
    assert labels[n // 2 * n + 1] == left
    assert labels[n // 2 * n + (n - 2)] == right
