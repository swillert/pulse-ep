"""Compare two EP maps — a ΔV-style field via nearest-neighbour correspondence.

The two maps share the study coordinate frame but may have different meshes
(e.g. a pre-ablation voltage map vs. a remap). For every vertex of ``map_a``
we find the corresponding value on ``map_b`` and subtract, yielding a delta
field on ``map_a``'s geometry. The correspondence metric is configurable:

- ``"euclidean"`` — the straight-line-nearest ``map_b`` vertex (a KD-tree);
- ``"geodesic"``  — the nearest source *along ``map_a``'s surface*: ``map_b``'s
  values are placed on their nearest ``map_a`` vertices and a multi-source
  Dijkstra over ``map_a``'s mesh assigns each vertex the geodesically-nearest
  one. Propagation follows the surface, but the initial Euclidean projection
  must still be checked near folds and between unregistered maps.

Comparison is an *operation*, not stored state; results can be kept as a
derived map (``kind = voltage_delta``) or a report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree


@dataclass
class ComparisonResult:
    """Per-``map_a``-vertex delta plus the correspondence it came from."""

    delta: np.ndarray  # a_value - b_value_at_correspondence
    b_values: np.ndarray  # map_b's scalar mapped onto map_a's vertices
    distances: np.ndarray  # correspondence distance (euclidean or geodesic)
    metric: str
    scalar_name: str
    n_masked: int  # vertices dropped to NaN because distance > max_distance

    def stats(self) -> dict:
        d = self.delta
        finite = np.isfinite(d)
        if not finite.any():
            return {"n": 0, "min": None, "max": None, "mean": None, "median": None}
        v = d[finite]
        return {
            "n": int(finite.sum()),
            "min": float(np.min(v)),
            "max": float(np.max(v)),
            "mean": float(np.mean(v)),
            "median": float(np.median(v)),
        }


def _mesh_graph(vertices: np.ndarray, triangles: np.ndarray):
    """Sparse, symmetric edge graph with euclidean edge lengths as weights."""
    edges = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    i, j = edges[:, 0], edges[:, 1]
    weights = np.linalg.norm(vertices[i] - vertices[j], axis=1)
    n = len(vertices)
    return coo_matrix(
        (np.concatenate([weights, weights]), (np.concatenate([i, j]), np.concatenate([j, i]))),
        shape=(n, n),
    ).tocsr()


def _euclidean(a_verts, b_verts, b_vals):
    dist, idx = cKDTree(b_verts).query(a_verts, k=1)
    return b_vals[idx], dist


def _geodesic(a_verts, a_tris, b_verts, b_vals, solver):
    # place each B value on its nearest A vertex (keep the closest B per A vertex)
    d_ab, a_idx = cKDTree(a_verts).query(b_verts, k=1)
    source_val: dict[int, float] = {}
    source_best: dict[int, float] = {}
    for jb, ai in enumerate(a_idx):
        ai = int(ai)
        if ai not in source_best or d_ab[jb] < source_best[ai]:
            source_best[ai] = float(d_ab[jb])
            source_val[ai] = float(b_vals[jb])
    sources = np.fromiter(source_val.keys(), dtype=int)

    if solver == "dijkstra":
        # graph distance along mesh edges — fast, gives the nearest source directly
        dist, _pred, nearest = dijkstra(
            _mesh_graph(a_verts, a_tris),
            directed=False,
            indices=sources,
            min_only=True,
            return_predecessors=True,
        )
    elif solver == "heat":
        # Heat Method — smoother/more accurate distance across faces, not just edges
        from pulse_ep.core.geodesic import heat_geodesic, nearest_source

        dist = heat_geodesic(a_verts, a_tris, sources)
        nearest = nearest_source(a_verts, a_tris, sources, dist)
    else:
        raise ValueError(f"unknown geodesic_solver {solver!r} (use 'dijkstra' or 'heat')")

    b_at = np.array([source_val.get(int(s), np.nan) for s in nearest])
    return b_at, dist


def compare_maps(
    map_a,
    map_b,
    scalar_name: str,
    metric: str = "euclidean",
    max_distance: float | None = None,
    geodesic_solver: str = "dijkstra",
) -> ComparisonResult:
    """Delta of ``scalar_name`` from ``map_b`` onto ``map_a`` (a - b).

    ``metric``: ``"euclidean"`` or ``"geodesic"``. For geodesic, ``geodesic_solver``
    selects ``"dijkstra"`` (edge-graph shortest path) or ``"heat"`` (Heat Method,
    smoother/more accurate across faces).
    """
    a_vals = np.asarray(map_a.get_scalar(scalar_name), dtype=float)
    b_vals = np.asarray(map_b.get_scalar(scalar_name), dtype=float)
    a_verts = np.asarray(map_a.vertices, dtype=float)
    b_verts = np.asarray(map_b.vertices, dtype=float)

    if metric == "euclidean":
        b_at, dist = _euclidean(a_verts, b_verts, b_vals)
    elif metric == "geodesic":
        b_at, dist = _geodesic(
            a_verts, np.asarray(map_a.triangles), b_verts, b_vals, geodesic_solver
        )
    else:
        raise ValueError(f"unknown metric {metric!r} (use 'euclidean' or 'geodesic')")

    delta = a_vals - b_at
    n_masked = 0
    if max_distance is not None:
        mask = dist > max_distance
        delta = delta.copy()
        b_at = b_at.copy()
        delta[mask] = np.nan
        b_at[mask] = np.nan
        n_masked = int(mask.sum())

    return ComparisonResult(delta, b_at, dist, metric, scalar_name, n_masked)
