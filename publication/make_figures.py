#!/usr/bin/env python3
"""Generate every figure for the publication from the synthetic fixtures.

No patient data is involved and none is needed: the two shipped exports in
``tests/fixtures/synthetic/`` are read the same way a clinical export is, so
each figure is the output of the real pipeline — and anyone can reproduce it
from a clean checkout.

    python publication/make_figures.py [--out publication/figures]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display in CI, and none needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402

import pulse_ep.core.importers  # noqa: E402, F401  — registers the vendor importers
from pulse_ep.core.comparison import compare_maps  # noqa: E402
from pulse_ep.core.importers.base import commit_plan, detect_vendor, prepare_plan  # noqa: E402
from pulse_ep.core.importers.source import source_for  # noqa: E402

pv.OFF_SCREEN = True  # never try to open a window, even if a display exists

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "synthetic"

# One look for every figure, so they sit together on a page.
plt.rcParams.update(
    {
        "figure.dpi": 200,
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
    }
)


def load(vendor: str):
    """The single map in a vendor's synthetic export, ready to render."""
    source = source_for(FIXTURES / vendor / "synthetic_study")
    importer = detect_vendor(source)
    if importer is None:
        raise SystemExit(f"no importer recognised {vendor}")
    (epmap,) = [
        m
        for study in commit_plan(importer, prepare_plan(importer, source), source)
        for m in study.epmaps
    ]
    epmap.generate_anatomical_pv_mesh(simplify=False)
    epmap.precompute_areas()
    # area_of_range() reads the scalar off the PyVista mesh, not off the
    # ScalarField, so every field has to be handed over explicitly.
    for name in epmap.scalar_fields:
        epmap.set_scalars(name, np.asarray(epmap.get_scalar(name), float))
    return epmap


def _polydata(epmap, values, name: str) -> pv.PolyData:
    faces = np.hstack([np.full((len(epmap.triangles), 1), 3), epmap.triangles]).ravel()
    mesh = pv.PolyData(np.asarray(epmap.vertices, float), faces)
    mesh.point_data[name] = np.asarray(values, float)
    return mesh


def _render(mesh, name, cmap, clim, title, path: Path, *, points=None, view="yz") -> None:
    """One off-screen render, on a plain light ground with a labelled bar."""
    pl = pv.Plotter(off_screen=True, window_size=(900, 800))
    pl.set_background("white")
    pl.add_mesh(
        mesh,
        scalars=name,
        cmap=cmap,
        clim=clim,
        smooth_shading=True,
        nan_color="lightgrey",
        scalar_bar_args={
            "title": title,
            "vertical": True,
            "position_x": 0.85,
            "position_y": 0.25,
            "height": 0.5,
            "width": 0.06,
            "title_font_size": 20,
            "label_font_size": 16,
            "color": "black",
        },
    )
    if points is not None and len(points):
        pl.add_points(
            np.asarray(points, float),
            color="black",
            point_size=6,
            render_points_as_spheres=True,
        )
    # The scar and the earliest site both sit on the x axis, so look
    # down it: edge-on, the interesting half of the map is invisible.
    pl.camera_position = view
    pl.camera.zoom(1.3)
    pl.screenshot(str(path))
    pl.close()


def fig_maps(maps: dict, out: Path) -> list[Path]:
    """Each vendor's map, coloured by its primary field, with its points."""
    written = []
    for vendor, epmap in maps.items():
        field = "activation_time" if vendor == "carto" else "voltage_bipolar"
        if field not in epmap.scalar_fields:
            field = next(iter(epmap.scalar_fields))
        values = epmap.get_scalar(field)
        label = {"activation_time": "LAT [ms]", "voltage_bipolar": "Bipolar [mV]"}.get(field, field)
        cmap = "jet_r" if field == "activation_time" else "jet"

        positions = [p.position for p in epmap.measurement_points if p.position is not None]
        path = out / f"map_{vendor}.png"
        _render(
            _polydata(epmap, values, field),
            field,
            cmap,
            (float(np.nanmin(values)), float(np.nanmax(values))),
            label,
            path,
            points=positions,
        )
        written.append(path)
    return written


def fig_area_per_interval(epmap, out: Path) -> Path:
    """The area breakdown that every client in examples/ reproduces."""
    field = "voltage_bipolar"
    values = np.asarray(epmap.get_scalar(field), float)
    edges = np.linspace(np.nanmin(values), np.nanmax(values), 9)
    areas = [
        epmap.area_of_range(lo, hi, scalar_name=field, include_upper=hi == edges[-1])
        for lo, hi in zip(edges[:-1], edges[1:])  # noqa: B905
    ]
    centres = (edges[:-1] + edges[1:]) / 2

    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.bar(centres, areas, width=np.diff(edges) * 0.9, color="#3b6ea5", edgecolor="white")
    ax.set_xlabel("Bipolar voltage [mV]")
    ax.set_ylabel("Surface area [cm²]")
    ax.set_title(f"Area per voltage interval — total {sum(areas):.2f} cm²")
    fig.tight_layout()
    path = out / "area_per_interval.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_cross_vendor_delta(maps: dict, out: Path) -> Path:
    """CARTO minus EnSiteX on the same surface, via compare_maps().

    Both fixtures carry the *same* field, so this is not a clinical delta: it
    is what the two decode paths disagree about, drawn with the same operation
    a real map-vs-map comparison uses. The residual is the formats' own
    coordinate and value precision — CARTO stores three decimals — not a
    difference in interpretation.
    """
    a, b = maps["carto"], maps["ensite"]
    result = compare_maps(a, b, "voltage_bipolar", metric="euclidean")
    delta = np.asarray(result.delta, float)
    limit = float(np.nanmax(np.abs(delta))) or 1.0
    print(f"  cross-vendor residual: max |Δ| = {limit:.2e} mV")

    path = out / "cross_vendor_delta.png"
    _render(
        _polydata(a, delta, "delta"),
        "delta",
        "coolwarm",
        (-limit, limit),
        "Δ Bipolar [mV]",
        path,
    )
    return path


def fig_histogram(maps: dict, out: Path) -> Path:
    """Both vendors' scalar distributions, from the same underlying surface."""
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.0))
    for ax, (vendor, epmap) in zip(axes, sorted(maps.items())):  # noqa: B905
        field = "voltage_bipolar"
        values = np.asarray(epmap.get_scalar(field), float)
        values = values[np.isfinite(values)]
        ax.hist(values, bins=24, color="#3b6ea5", edgecolor="white")
        ax.set_title(f"{vendor} — {field}")
        ax.set_xlabel("mV")
        ax.set_ylabel("vertices")
    fig.tight_layout()
    path = out / "scalar_histograms.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "figures")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    maps = {v: load(v) for v in ("carto", "ensite")}
    written = fig_maps(maps, args.out)
    written.append(fig_area_per_interval(maps["ensite"], args.out))
    written.append(fig_cross_vendor_delta(maps, args.out))
    written.append(fig_histogram(maps, args.out))

    for path in written:
        try:
            shown = path.relative_to(REPO)
        except ValueError:  # --out may point anywhere
            shown = path
        print(f"  {shown}  ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
