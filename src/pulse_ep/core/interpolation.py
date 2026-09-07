"""Turning scattered measurements into a surface field.

A map is measured at a few thousand points but displayed on a mesh of tens of
thousands of vertices, so something has to decide what every other vertex
shows. There are two different answers, and pulse-ep only ever had the first:

``mask``
    Trust the vendor. CARTO and EnSite X already write an interpolated value
    per vertex; we only hide the ones too far from any real measurement. This
    is what :meth:`EPMap.interpolate_scalar_values` has always done — despite
    its name it interpolates nothing, it masks.

``gaussian`` / ``geodesic``
    Compute the field ourselves from the measurement points, so the result is
    reproducible from the raw data and independent of the vendor's own
    (undocumented, version-dependent) interpolation.

The two computed methods differ in how distance is measured. ``gaussian``
weights by straight-line distance: fast, and wrong wherever the surface folds
back on itself — a point on the far side of a thin wall is millimetres away
through blood and centimetres away along tissue. ``geodesic`` measures along
the surface instead.

The `geodesic` method uses normalised diffusion on the mesh: it projects
measurements to mesh vertices, applies a discrete implicit heat step to the
values and to their sampling weights, then divides the results. The heat
kernel's short-time relation to surface distance motivates this smoothing;
the discrete solve is not an exact Gaussian weighting by geodesic distance.
Results depend on mesh resolution, source projection and the diffusion scale.

Cyclic quantities ("early meets late")
--------------------------------------
Averaging activation times across the wrap-around of a reentrant circuit is
meaningless: 5 ms and 295 ms of a 300 ms cycle are neighbours in time, but
their arithmetic mean is 150 ms — the far side of the circuit, and a line of
false "block" straight through the wavefront. With ``cycle_length`` the values
are carried onto the unit circle, interpolated there, and brought back, so
early and late meet the way they do in the patient.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

from pulse_ep.core.geodesic import heat_geodesic, laplacian_mass

#: How a vertex value is decided. ``mask`` keeps the vendor's own field.
METHODS = ("mask", "gaussian", "geodesic")

#: Neighbours considered per vertex for the Euclidean kernel. Bounded rather
#: than radius-based so cost stays predictable on a dense map; beyond ~3σ the
#: Gaussian weight is negligible anyway.
_KERNEL_NEIGHBOURS = 16


def default_sigma(source_points: np.ndarray) -> float:
    """A kernel width from the data's own spacing.

    The median nearest-neighbour distance between measurement points: wide
    enough to close the gaps between them, narrow enough not to smear detail
    the operator took the trouble to acquire.
    """
    pts = np.asarray(source_points, dtype=float)
    if len(pts) < 2:
        return 1.0
    tree = cKDTree(pts)
    nn = tree.query(pts, k=2)[0][:, 1]
    nn = nn[np.isfinite(nn) & (nn > 0)]
    return float(np.median(nn)) if nn.size else 1.0


def _resolve_cycle_length(values: np.ndarray, cycle_length: float | None) -> float | None:
    """The cycle length to wrap on: ``0`` means "infer it from the data"."""
    if cycle_length is None:
        return None
    if cycle_length == 0:
        finite = values[np.isfinite(values)]
        cycle_length = float(finite.max() - finite.min()) if finite.size else 0.0
    return cycle_length if cycle_length > 0 else None


def _to_circle(values: np.ndarray, cycle_length: float) -> tuple[np.ndarray, np.ndarray]:
    """Values as points on the unit circle (real, imaginary parts)."""
    phase = 2.0 * np.pi * values / cycle_length
    return np.cos(phase), np.sin(phase)


def _from_circle(real: np.ndarray, imag: np.ndarray, cycle_length: float, origin: float):
    """Back from the circle, into the window the input values lived in."""
    values = np.angle(real + 1j * imag) / (2.0 * np.pi) * cycle_length
    return origin + np.mod(values - origin, cycle_length)


def _clean(source_points, values):
    """Drop measurements with no value — an unannotated point is not a zero."""
    pts = np.asarray(source_points, dtype=float)
    vals = np.asarray(values, dtype=float)
    if len(pts) != len(vals):
        raise ValueError(f"{len(pts)} measurement positions but {len(vals)} values")
    keep = np.isfinite(vals) & np.isfinite(pts).all(axis=1)
    return pts[keep], vals[keep]


def gaussian_interpolate(
    mesh_points,
    source_points,
    values,
    sigma: float | None = None,
    distance_threshold: float | None = None,
    cycle_length: float | None = None,
) -> np.ndarray:
    """Gaussian-weighted average of nearby measurements, by straight-line distance.

    :param sigma: kernel width; defaults to :func:`default_sigma`.
    :param distance_threshold: vertices farther than this from any measurement
        are ``NaN`` — the same confidence mask the vendor field gets.
    :param cycle_length: wrap values cyclically (``0`` = infer). See the module
        docstring.
    :returns: one value per mesh point, ``NaN`` where nothing was measured.
    """
    pts, vals = _clean(source_points, values)
    mesh = np.asarray(mesh_points, dtype=float)
    if pts.size == 0:
        return np.full(len(mesh), np.nan)

    sigma = float(sigma) if sigma else default_sigma(pts)
    tree = cKDTree(pts)
    k = min(_KERNEL_NEIGHBOURS, len(pts))
    distances, idx = tree.query(mesh, k=k)
    if k == 1:
        distances, idx = distances[:, None], idx[:, None]

    weights = np.exp(-(distances**2) / (2.0 * sigma**2))
    total = weights.sum(axis=1)

    cl = _resolve_cycle_length(vals, cycle_length)
    if cl is None:
        out = (weights * vals[idx]).sum(axis=1) / total
    else:
        real, imag = _to_circle(vals, cl)
        out = _from_circle(
            (weights * real[idx]).sum(axis=1) / total,
            (weights * imag[idx]).sum(axis=1) / total,
            cl,
            float(vals[np.isfinite(vals)].min()),
        )

    # Nothing within reach of the kernel is not "the mean of far-away points".
    out[total <= 0] = np.nan
    if distance_threshold is not None:
        out[distances[:, 0] > distance_threshold] = np.nan
    return out


def heat_interpolate(
    vertices,
    triangles,
    source_vertices,
    values,
    sigma: float | None = None,
    distance_threshold: float | None = None,
    cycle_length: float | None = None,
) -> np.ndarray:
    """Normalised discrete diffusion of measurements along the mesh surface.

    ``source_vertices`` are the vertex indices the measurements project onto
    (several measurements may share one vertex — they are averaged there).

    Uses one implicit diffusion step with ``t = sigma**2 / 2``, floored at
    the squared mean length of the first edge of each triangle. This is a
    mesh-dependent smoothing approximation, not an exact Gaussian convolution
    in geodesic distance.

    :param distance_threshold: masked geodesically as well, so the boundary of
        the shown region follows the tissue rather than the air gap.
    """
    V = np.asarray(vertices, dtype=float)
    F = np.asarray(triangles)
    idx = np.asarray(source_vertices, dtype=int)
    vals = np.asarray(values, dtype=float)

    keep = np.isfinite(vals)
    idx, vals = idx[keep], vals[keep]
    if idx.size == 0:
        return np.full(len(V), np.nan)

    if sigma is None or not sigma:
        sigma = default_sigma(V[idx]) if len(idx) > 1 else 1.0

    L, mass = laplacian_mass(V, F)
    edge_length = np.sqrt(np.sum((V[F[:, 0]] - V[F[:, 1]]) ** 2, axis=1)).mean()
    t = max(float(sigma) ** 2 / 2.0, edge_length**2)
    solve = factorized((diags(mass) - t * L).tocsc())

    # count of measurements per vertex — the denominator of the weighted mean
    density = np.zeros(len(V))
    np.add.at(density, idx, 1.0)
    weight = solve(density)

    def _diffuse(per_measurement: np.ndarray) -> np.ndarray:
        acc = np.zeros(len(V))
        np.add.at(acc, idx, per_measurement)
        return solve(acc)

    cl = _resolve_cycle_length(vals, cycle_length)
    with np.errstate(invalid="ignore", divide="ignore"):
        if cl is None:
            out = _diffuse(vals) / weight
        else:
            real, imag = _to_circle(vals, cl)
            out = _from_circle(
                _diffuse(real) / weight,
                _diffuse(imag) / weight,
                cl,
                float(vals.min()),
            )

    # Where essentially no heat arrived, no measurement is in reach.
    reachable = weight > weight.max() * 1e-6
    out = np.where(reachable, out, np.nan)

    if distance_threshold is not None:
        distance = heat_geodesic(V, F, np.unique(idx))
        out[distance > distance_threshold] = np.nan
    return out
