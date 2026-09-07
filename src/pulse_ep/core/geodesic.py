"""Geodesic distance on a triangle mesh — the Heat Method (Crane et al. 2013).

Heat flow gives smoother, more accurate geodesic distances than a Dijkstra
walk over mesh edges (which can only travel along edges and so overestimates).
``heat_geodesic`` returns the distance from a set of source vertices to every
vertex; ``nearest_source`` labels each vertex with the source it is
geodesically closest to (using the heat field to order propagation).
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, diags
from scipy.sparse.linalg import factorized


def _cotan_laplacian_mass(V: np.ndarray, F: np.ndarray):
    """Cotangent Laplacian ``L`` (negative-semidefinite: off-diag > 0, diag < 0)
    and lumped vertex-area mass diagonal ``m``."""
    n = len(V)
    i1, i2, i3 = F[:, 0], F[:, 1], F[:, 2]
    v1, v2, v3 = V[i1], V[i2], V[i3]
    # squared edge lengths, edge opposite each vertex
    l1 = np.sum((v2 - v3) ** 2, axis=1)
    l2 = np.sum((v3 - v1) ** 2, axis=1)
    l3 = np.sum((v1 - v2) ** 2, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(v2 - v1, v3 - v1), axis=1)
    area = np.maximum(area, 1e-12)
    # cot of the angle at each vertex = (sum of the two adjacent squared edges - opposite) / (4 area)
    cot1 = (l2 + l3 - l1) / (4.0 * area)
    cot2 = (l3 + l1 - l2) / (4.0 * area)
    cot3 = (l1 + l2 - l3) / (4.0 * area)
    # edge weight = cot(opposite angle) / 2, symmetric
    w = 0.5 * np.concatenate([cot1, cot1, cot2, cot2, cot3, cot3])
    ii = np.concatenate([i2, i3, i3, i1, i1, i2])
    jj = np.concatenate([i3, i2, i1, i3, i2, i1])
    off = coo_matrix((w, (ii, jj)), shape=(n, n)).tocsr()
    rowsum = np.asarray(off.sum(axis=1)).ravel()
    L = (off - diags(rowsum)).tocsc()  # L_ii = -sum(off), L_ij = w_ij

    m = np.zeros(n)
    for idx in (i1, i2, i3):
        np.add.at(m, idx, area / 3.0)
    return L, m


def laplacian_mass(vertices, triangles):
    """Public entry to the cotangent Laplacian ``L`` and lumped mass ``m``.

    Diffusion on a mesh is not only the Heat Method's business — scattered
    data interpolation (:mod:`~pulse_ep.core.interpolation`) solves with the
    same operator — so it is offered rather than re-derived.
    """
    return _cotan_laplacian_mass(np.asarray(vertices, dtype=float), np.asarray(triangles))


def _face_gradient(V, F, u):
    """Per-face gradient of a per-vertex scalar ``u``."""
    v1, v2, v3 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    normal = np.cross(v2 - v1, v3 - v1)
    area2 = np.linalg.norm(normal, axis=1, keepdims=True)
    n_hat = normal / np.maximum(area2, 1e-12)
    # gradient = (1/2A) sum u_i * (N x opposite-edge)
    g = (
        u[F[:, 0]][:, None] * np.cross(n_hat, v3 - v2)
        + u[F[:, 1]][:, None] * np.cross(n_hat, v1 - v3)
        + u[F[:, 2]][:, None] * np.cross(n_hat, v2 - v1)
    )
    return g / np.maximum(area2, 1e-12)


def _divergence(V, F, X, n):
    """Integrated divergence at each vertex of a per-face vector field ``X``."""
    v1, v2, v3 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    l1 = np.sum((v2 - v3) ** 2, axis=1)
    l2 = np.sum((v3 - v1) ** 2, axis=1)
    l3 = np.sum((v1 - v2) ** 2, axis=1)
    area = np.maximum(0.5 * np.linalg.norm(np.cross(v2 - v1, v3 - v1), axis=1), 1e-12)
    cot1 = (l2 + l3 - l1) / (4.0 * area)
    cot2 = (l3 + l1 - l2) / (4.0 * area)
    cot3 = (l1 + l2 - l3) / (4.0 * area)
    e1, e2, e3 = v2 - v1, v3 - v2, v1 - v3  # edges (1->2, 2->3, 3->1)
    div = np.zeros(n)
    # contribution at each vertex from its two incident edges in the face
    np.add.at(div, F[:, 0], 0.5 * (cot3 * np.sum(e1 * X, axis=1) - cot2 * np.sum(e3 * X, axis=1)))
    np.add.at(div, F[:, 1], 0.5 * (cot1 * np.sum(e2 * X, axis=1) - cot3 * np.sum(e1 * X, axis=1)))
    np.add.at(div, F[:, 2], 0.5 * (cot2 * np.sum(e3 * X, axis=1) - cot1 * np.sum(e2 * X, axis=1)))
    return div


def heat_geodesic(vertices, triangles, sources, m: float = 1.0) -> np.ndarray:
    """Geodesic distance from ``sources`` to every vertex via the Heat Method.

    :param m: time-step factor ``t = m * mean_edge_length**2`` (Crane default 1).
    """
    V = np.asarray(vertices, dtype=float)
    F = np.asarray(triangles)
    n = len(V)
    sources = np.atleast_1d(np.asarray(sources, dtype=int))

    L, mass = _cotan_laplacian_mass(V, F)
    edge_len = np.sqrt(np.sum((V[F[:, 0]] - V[F[:, 1]]) ** 2, axis=1)).mean()
    t = m * edge_len**2

    # 1) heat flow: (Mass - t L) u = u0
    u0 = np.zeros(n)
    u0[sources] = 1.0
    heat_op = (diags(mass) - t * L).tocsc()
    u = factorized(heat_op)(u0)

    # 2) normalised reverse gradient
    grad = _face_gradient(V, F, u)
    norms = np.linalg.norm(grad, axis=1, keepdims=True)
    X = -grad / np.maximum(norms, 1e-12)

    # 3) Poisson: L phi = div X  (pin the sources to remove the constant nullspace)
    b = _divergence(V, F, X, n)
    Lp = L.tolil()
    for s in sources:
        Lp.rows[s] = [s]
        Lp.data[s] = [1.0]
        b[s] = 0.0
    phi = factorized(csr_matrix(Lp).tocsc())(b)
    phi -= phi[sources].min()
    return np.abs(phi)


def nearest_source(vertices, triangles, sources, dist_field: np.ndarray) -> np.ndarray:
    """Label each vertex with the source it is geodesically closest to, using
    ``dist_field`` (e.g. from :func:`heat_geodesic`) to order propagation."""
    F = np.asarray(triangles)
    n = len(vertices)
    sources = np.atleast_1d(np.asarray(sources, dtype=int))

    # neighbour lists
    neigh: list[list[int]] = [[] for _ in range(n)]
    for a, b in np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]):
        neigh[a].append(b)
        neigh[b].append(a)

    label = np.full(n, -1, dtype=int)
    label[sources] = sources
    for v in np.argsort(dist_field):
        if label[v] != -1:
            continue
        best, best_d = -1, np.inf
        for w in neigh[v]:
            if label[w] != -1 and dist_field[w] < best_d:
                best, best_d = w, dist_field[w]
        if best != -1:
            label[v] = label[best]
    return label
