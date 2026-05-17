#!/usr/bin/env python3
"""
Generate fig_heatmap.pdf — 3D surface renders of representative pace maps.

Based on generate_heatmap_surface.py (PyVista rendering),
adapted for CMPB journal style (English labels, clean layout).

Three panels showing different degrees of spatial focality:
  A: Focal map (LA posterior, single-chamber, σ = 6.7 mm)
  B: Diffuse map (RA lateral, single-chamber, σ = 36.2 mm)
  C: Focal map under double-chamber reference (RA lateral, σ = 4.7 mm)

Requires: pulse_ep (database access), pyvista, matplotlib
Run from pulse-ultimate root with venv active:
    python generate_heatmap_journal.py

Output: thesis-med/_paper/method-paper/figs/fig_heatmap.pdf

Author: Sven Willert, UKSH Kiel
"""

import matplotlib

matplotlib.use("Agg")
import os

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.colors import LinearSegmentedColormap
from scipy.spatial import cKDTree

from pulse_ep.core import plot_proc as plot_proc
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel, EPMapPoint

DISTANCE_THRESHOLD = 8  # mm — vertices further from any measurement point shown as grey

# ─── Paths ─────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPATH = os.path.join(
    SCRIPT_DIR, "..", "thesis-med", "_paper", "method-paper", "figs", "fig_heatmap.pdf"
)
OUTPATH = os.path.normpath(OUTPATH)
TMP_DIR = "/tmp/heatmap_panels_cmpb"

# ─── Journal style ─────────────────────────────────────────
GRAY_DARK = "#333333"
GRAY_MID = "#76787A"
GRAY_LIGHT = "#D9D9D9"
BG_WHITE = "#FFFFFF"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 9,
        "figure.facecolor": BG_WHITE,
        "figure.dpi": 300,
        "savefig.facecolor": BG_WHITE,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    }
)

# ─── Panels ────────────────────────────────────────────────
PANELS = [
    {
        "map_id": 75,
        "title": "LA posterior",
        "sigma": "6.7",
        "r2": "0.99",
        "letter": "A",
        "atrium": "LA",
        "direction": "PA",
    },
    {
        "map_id": 78,
        "title": "RA lateral",
        "sigma": "36.2",
        "r2": "0.86",
        "letter": "B",
        "atrium": "RA",
        "direction": "RL",
    },
    {
        "map_id": 25,
        "title": "RA lateral",
        "sigma": "4.7",
        "r2": "0.98",
        "letter": "C",
        "atrium": "RA",
        "direction": "RL",
    },
]

# ─── Colormap (matching platform) ─────────────────────────
# For the matplotlib colorbar — matches the PyVista cmap
cbar_cmap = LinearSegmentedColormap.from_list(
    "heat",
    [
        (0.00, "#1C2833"),
        (0.30, "#1A5276"),
        (0.50, "#00857C"),
        (0.68, "#F4D03F"),
        (0.82, "#E67E22"),
        (1.00, "#E3120B"),
    ],
)


def render_panel(session, panel_info, output_png):
    """Render a single mesh panel using PyVista, with distance-based masking."""
    map_id = panel_info["map_id"]

    # Load mesh from DB
    epmap_model = EPMapModel.find_by_id(map_id, session)
    if epmap_model is None:
        raise ValueError(f"Map {map_id} not found")

    vertices = np.array(epmap_model.vertices).reshape(-1, 3)
    triangles = np.array(epmap_model.triangles).reshape(-1, 3)
    act_bip = np.array(epmap_model.act_bip).reshape(-1, 2)

    # Load measurement point positions from DB
    point_rows = (
        session.query(EPMapPoint.position_x, EPMapPoint.position_y, EPMapPoint.position_z)
        .filter(EPMapPoint.map_id == map_id, EPMapPoint.position_x != None)  # noqa: E711
        .all()
    )
    point_xyz = np.array([[r[0], r[1], r[2]] for r in point_rows])
    print(
        f"  Map {map_id}: {len(vertices)} vertices, {len(triangles)} faces, "
        f"{len(point_xyz)} measurement points"
    )

    # Build PyVista mesh
    faces_pv = np.pad(triangles, ((0, 0), (1, 0)), "constant", constant_values=3)
    pv_mesh = pv.PolyData(vertices, faces_pv)

    # Matching scores: abs of activation column
    scalar_data = act_bip[:, 0].copy()
    if np.nanmax(scalar_data) < 0:
        scalar_data = -scalar_data

    # Normalize to 0-100
    max_val = np.nanmax(scalar_data)
    if max_val != 0:
        scalar_data = (scalar_data / max_val) * 100

    # Distance masking: NaN for vertices far from measurement points
    tree = cKDTree(point_xyz)
    distances, _ = tree.query(vertices)
    far_mask = distances > DISTANCE_THRESHOLD
    scalar_data[far_mask] = np.nan
    n_masked = far_mask.sum()
    print(
        f"  Distance mask ({DISTANCE_THRESHOLD} mm): {n_masked}/{len(vertices)} "
        f"vertices masked ({n_masked / len(vertices) * 100:.0f}%)"
    )

    pv_mesh.point_data["act"] = scalar_data

    # Colormap: same as platform
    cmap = plot_proc.create_modified_hsv_colormap()
    clim = [50, 100]

    # Camera direction (same as generate_heatmap_surface.py / EPMap.plot_mesh)
    direction = panel_info["direction"]
    atrium = panel_info["atrium"]

    if direction == "AP":
        view_vector = np.array([0, 0, 1])
        up_vector = np.array([0, 1, 0])
    elif direction == "PA":
        view_vector = np.array([0, 0, -1])
        up_vector = np.array([0, 1, 0])
    elif direction == "RL":
        if atrium == "RA":
            view_vector = np.array([1, 0, 0])
            up_vector = np.array([1, 1, 0])
        else:
            view_vector = np.array([-1, 0, 0])
            up_vector = np.array([0, 0, -1])

    # Render with white background for journal style
    plotter = pv.Plotter(window_size=(1200, 1000), off_screen=True)
    plotter.set_background("#1C2833")

    plotter.add_mesh(
        pv_mesh,
        scalars="act",
        cmap=cmap,
        clim=clim,
        show_scalar_bar=False,
        nan_color="#BDBDBD",
        nan_opacity=0.4,
    )

    # Mark origin (highest-score vertex)
    # Offset along vertex normal so it's always visible above the surface
    valid_mask = ~np.isnan(scalar_data)
    if valid_mask.any():
        origin_idx = np.nanargmax(scalar_data)
        origin_pt = vertices[origin_idx].copy()

        # Compute vertex normal from adjacent faces
        pv_mesh.compute_normals(cell_normals=False, point_normals=True, inplace=True)
        normal = pv_mesh.point_normals[origin_idx]
        # Offset 2mm along normal so the marker sits above the surface
        origin_pt_offset = origin_pt + normal * 2.0

        origin_mesh = pv.PolyData(origin_pt_offset.reshape(1, 3))
        plotter.add_mesh(
            origin_mesh, color="white", point_size=18, render_points_as_spheres=True, style="points"
        )

    plotter.view_vector(view_vector, up_vector)
    plotter.screenshot(output_png, transparent_background=False)
    plotter.close()
    print(f"  Rendered map {map_id} → {output_png}")


def compose_figure(panel_pngs):
    """Compose PyVista renders into journal-style figure."""

    fig = plt.figure(figsize=(7.5, 3.5), facecolor=BG_WHITE)

    gs = fig.add_gridspec(
        1,
        4,
        width_ratios=[1, 1, 1, 0.05],
        left=0.03,
        right=0.97,
        bottom=0.05,
        top=0.88,
        wspace=0.08,
    )

    for i, (panel, png_path) in enumerate(zip(PANELS, panel_pngs)):  # noqa: B905
        ax = fig.add_subplot(gs[0, i])
        img = mpimg.imread(png_path)
        ax.imshow(img)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#2C3E50")
            spine.set_linewidth(0.6)

        # Panel label and annotations
        ax.text(
            -0.06,
            1.10,
            panel["letter"],
            transform=ax.transAxes,
            fontsize=14,
            fontweight="bold",
            color=GRAY_DARK,
            va="top",
        )
        ax.text(
            0.06,
            1.08,
            panel["title"],
            transform=ax.transAxes,
            fontsize=9,
            fontweight="bold",
            color=GRAY_DARK,
            va="top",
        )

        # σ and R² in overlay box
        box_text = f"σ = {panel['sigma']} mm\n$R^2$ = {panel['r2']}"
        ax.text(
            0.97,
            0.04,
            box_text,
            transform=ax.transAxes,
            fontsize=7,
            color="#D5D8DC",
            va="bottom",
            ha="right",
            fontfamily="monospace",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="#1C2833",
                edgecolor="#2C3E50",
                linewidth=0.5,
                alpha=0.88,
            ),
        )

    # Colorbar
    cax = fig.add_subplot(gs[0, 3])
    sm = plt.cm.ScalarMappable(cmap=cbar_cmap, norm=plt.Normalize(vmin=50, vmax=100))
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label("Matching score (%)", fontsize=8, color=GRAY_DARK)
    cb.ax.tick_params(labelsize=7, colors=GRAY_MID)
    cb.outline.set_linewidth(0.4)
    cb.outline.set_edgecolor(GRAY_LIGHT)

    os.makedirs(os.path.dirname(OUTPATH), exist_ok=True)
    fig.savefig(OUTPATH, dpi=300)
    plt.close()
    print(f"\n  ✓ {OUTPATH}")


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs(TMP_DIR, exist_ok=True)

    print("Rendering mesh panels via PyVista...")
    panel_pngs = []

    with get_db_session() as session:
        for panel in PANELS:
            png_path = os.path.join(TMP_DIR, f"panel_{panel['map_id']}.png")
            render_panel(session, panel, png_path)
            panel_pngs.append(png_path)

    print("\nComposing journal-style figure...")
    compose_figure(panel_pngs)
