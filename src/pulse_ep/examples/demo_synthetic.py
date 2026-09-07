"""End-to-end demo of pulse-ep on a synthetic mesh.

Builds an atrium-like ellipsoid, paints a Gaussian-like pacemapping score
field onto its vertices, wraps it as an :class:`pulse_ep.EPMap` and prints
a summary (vertex/triangle counts, surface area, score distribution and a
per-interval area breakdown).

Runs **without** a database, so it works as a quickstart that exercises
just the array-only public API. Invoke from the shell with::

    pulse-ep-demo                      # default 530-vertex ellipsoid
    pulse-ep-demo --resolution 32      # higher mesh resolution
    pulse-ep-demo --sigma 8.0          # narrower / wider focal point
    pulse-ep-demo --show               # open a 3D viewer window
"""

from __future__ import annotations

import argparse

import numpy as np

from pulse_ep import EPMap


def make_synthetic_atrium(
    resolution: int = 24,
    radius_xyz: tuple[float, float, float] = (25.0, 25.0, 35.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(vertices, triangles)`` of an ellipsoidal pseudo-atrium.

    Uses ``pyvista.Sphere`` and then scales each axis so the result is
    elongated like a left-atrium-style chamber.

    Parameters
    ----------
    resolution
        Theta/phi resolution of the sphere — higher = denser mesh.
    radius_xyz
        Half-axes of the ellipsoid, in millimetres.
    """
    import pyvista as pv

    sphere = pv.Sphere(radius=1.0, theta_resolution=resolution, phi_resolution=resolution)
    sphere.points *= np.array(radius_xyz)
    triangles = sphere.faces.reshape(-1, 4)[:, 1:].astype(np.int64)
    return np.asarray(sphere.points), triangles


def gaussian_score_field(
    vertices: np.ndarray,
    origin_xyz: tuple[float, float, float] | None = None,
    sigma_mm: float = 6.0,
    rng: np.random.Generator | None = None,
    noise_std: float = 0.02,
) -> tuple[np.ndarray, int]:
    """Return a per-vertex score field shaped like a Gaussian peak in 3D.

    Score scale matches pace-mapping convention (0–100 %).
    """
    if rng is None:
        rng = np.random.default_rng(seed=42)
    if origin_xyz is None:
        origin_xyz = tuple(vertices[0])
    origin = np.asarray(origin_xyz)
    distances_euclidean = np.linalg.norm(vertices - origin, axis=1)
    scores = 100.0 * np.exp(-(distances_euclidean**2) / (2.0 * sigma_mm**2))
    if noise_std > 0:
        scores += rng.normal(0.0, noise_std * 100.0, size=scores.shape)
    scores = np.clip(scores, 0.0, 100.0)
    origin_idx = int(np.argmax(scores))
    return scores, origin_idx


def triangle_areas(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Return per-triangle areas of a mesh."""
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)


def area_breakdown(
    triangles: np.ndarray,
    tri_areas: np.ndarray,
    scores: np.ndarray,
    bins: np.ndarray,
) -> dict[tuple[float, float], float]:
    """Sum triangle area per score interval. Triangle score = mean of its vertices."""
    tri_scores = scores[triangles].mean(axis=1)
    out: dict[tuple[float, float], float] = {}
    for lo, hi in zip(bins[:-1], bins[1:]):  # noqa: B905
        mask = (tri_scores >= lo) & (tri_scores < hi)
        out[(float(lo), float(hi))] = float(tri_areas[mask].sum())
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pulse-ep-demo",
        description="Synthetic pulse-ep walkthrough: build an ellipsoidal atrium, "
        "paint a Gaussian pace-mapping field, and print an EPMap summary.",
    )
    parser.add_argument("--resolution", type=int, default=24, help="mesh theta/phi resolution")
    parser.add_argument("--sigma", type=float, default=6.0, help="Gaussian width in mm")
    parser.add_argument("--noise", type=float, default=0.02, help="relative noise std on scores")
    parser.add_argument("--show", action="store_true", help="open an interactive 3D viewer")
    args = parser.parse_args(argv)

    print("pulse-ep demo — synthetic atrium with a Gaussian pace-mapping field")
    print("-" * 72)

    vertices, triangles = make_synthetic_atrium(resolution=args.resolution)
    print(f"mesh:           {len(vertices)} vertices, {len(triangles)} triangles")

    scores, origin_idx = gaussian_score_field(vertices, sigma_mm=args.sigma, noise_std=args.noise)
    print(f"score field:    σ = {args.sigma:.1f} mm, origin vertex = {origin_idx}")
    print(
        f"                min/median/max = {scores.min():.1f} / "
        f"{np.median(scores):.1f} / {scores.max():.1f} %"
    )

    tri_areas = triangle_areas(vertices, triangles)
    total_area_cm2 = tri_areas.sum() / 100.0
    print(f"surface area:   {total_area_cm2:.2f} cm² (total)")

    # Build an EPMap with our synthetic content — this is the same domain
    # object the CARTO importer would produce.
    epmap = EPMap(
        map_name="synthetic_demo",
        study_name="pulse-ep demo",
        map_number_of_points=int(len(vertices)),
        triangles=triangles,
        vertices=vertices,
        # mm², the unit every importer stores and /get_mesh_data declares
        # (raw_export: units.triangle_areas = "mm^2"). area_of_surface() and
        # area_of_range() do not read this attribute — they recompute from the
        # PyVista mesh and convert to cm² themselves.
        triangle_areas=tri_areas,
        # act_bip[:,0] holds activation/score values by convention; the
        # synthetic score field stands in for matching-score data here.
        act_bip=np.column_stack([scores, np.zeros_like(scores)]),
    )
    epmap.register_scalar(
        "pacemap_score", scores, kind="pacemap_score", unit="%", source="synthetic"
    )
    print(f"EPMap:          name='{epmap.map_name}', study='{epmap.study_name}'")

    bins = np.array([0, 20, 40, 60, 80, 90, 95, 100, 101], dtype=float)
    table = area_breakdown(triangles, tri_areas, scores, bins)
    print()
    print("Area by score interval (mean of triangle vertices):")
    print(f"  {'interval (%)':>12}   {'area (cm²)':>12}   {'% of total':>11}")
    for (lo, hi), area in table.items():
        cm2 = area / 100.0
        pct = 100.0 * cm2 / total_area_cm2
        print(f"  [{lo:>4.0f}, {hi:>4.0f})   {cm2:>12.2f}   {pct:>10.1f} %")

    if args.show:
        try:
            import pyvista as pv
        except ImportError:
            print("pyvista not installed — install pulse-ep[server] or pulse-ep[all]")
            return 1
        faces = np.pad(triangles, ((0, 0), (1, 0)), "constant", constant_values=3)
        mesh = pv.PolyData(vertices, faces)
        mesh["score"] = scores
        plotter = pv.Plotter()
        plotter.add_mesh(mesh, scalars="score", cmap="magma", show_edges=False)
        plotter.add_text("pulse-ep demo — synthetic atrium", font_size=12)
        plotter.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
