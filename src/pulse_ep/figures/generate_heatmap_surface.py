#!/usr/bin/env python3
"""
Generate heatmap_vergleich.pdf — Economist-style frame, PyVista mesh renders.

Uses the same PyVista rendering pipeline as EPMap.plot_mesh() for the
three mesh panels, then composites them into an Economist-style figure.

Run from pulse-ultimate root with venv active:
    python generate_heatmap_surface.py

Output: thesis-med/_figures/heatmap_vergleich.pdf
"""

import matplotlib

matplotlib.use("Agg")
import os

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch
from scipy.spatial import cKDTree

from pulse_ep.core import plot_proc as plot_proc
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel, EPMapPoint

DISTANCE_THRESHOLD = 8  # mm — vertices further from any measurement point shown as grey

# ─── Economist palette ──────────────────────────────────────
RED = "#E3120B"
BLUE = "#006BA6"
TEAL = "#00857C"
GRAY_DARK = "#333333"
GRAY_MID = "#76787A"
GRAY_LIGHT = "#D9D9D9"
BG_CREAM = "#F7F5F0"
BG_WHITE = "#FFFFFF"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Source Sans 3", "Source Sans Pro", "Helvetica Neue"],
        "font.monospace": ["Source Code Pro", "Menlo"],
        "font.size": 10,
        "figure.facecolor": BG_WHITE,
        "figure.dpi": 200,
        "savefig.facecolor": BG_WHITE,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.12,
    }
)

# Economist-style colormap for the colorbar (matches the PyVista cmap)
econ_cmap = LinearSegmentedColormap.from_list(
    "econ_heat",
    [
        (0.00, "#1C2833"),
        (0.30, "#1A5276"),
        (0.50, TEAL),
        (0.68, "#F4D03F"),
        (0.82, "#E67E22"),
        (1.00, RED),
    ],
)

OUTPATH = os.environ.get(
    "PULSE_HEATMAP_OUTPATH",
    os.path.join(os.path.dirname(__file__), "heatmap_vergleich.pdf"),
)
TMP_DIR = os.environ.get("PULSE_HEATMAP_TMP", "/tmp/heatmap_panels")

# Map IDs and their metadata
PANELS = [
    {
        "map_id": 75,
        "title": "LA posterior",
        "subtitle": "Single-Chamber-Referenz",
        "sigma": "6,7",
        "area": "1,87",
        "letter": "A",
        "atrium": "LA",
        "direction": "PA",
    },
    {
        "map_id": 78,
        "title": "RA lateral",
        "subtitle": "Single-Chamber-Referenz",
        "sigma": "36,2",
        "area": "8,97",
        "letter": "B",
        "atrium": "RA",
        "direction": "RL",
    },
    {
        "map_id": 25,
        "title": "RA lateral",
        "subtitle": "Double-Chamber-Referenz",
        "sigma": "4,7",
        "area": "0,09",
        "letter": "C",
        "atrium": "RA",
        "direction": "RL",
    },
]


def render_panel(session, panel_info, output_png):
    """Render a single mesh panel using PyVista (same approach as EPMap.plot_mesh),
    with distance-based masking: vertices > DISTANCE_THRESHOLD mm from any
    measurement point are shown in light grey."""
    map_id = panel_info["map_id"]
    atrium = panel_info["atrium"]
    direction = panel_info["direction"]

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

    # Build PyVista mesh (same as EPMap.generate_anatomical_pv_mesh)
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
    # (same logic as EPMap.interpolate_scalar_values with distance_threshold)
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

    # Camera direction (same logic as EPMap.plot_mesh)
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

    # Render
    plotter = pv.Plotter(window_size=(1200, 1000), off_screen=True)
    plotter.set_background("#1C2833")

    # Add mesh with NaN → light grey (nan_color)
    plotter.add_mesh(
        pv_mesh,
        scalars="act",
        cmap=cmap,
        clim=clim,
        show_scalar_bar=False,
        nan_color="#BDBDBD",
        nan_opacity=0.4,
    )

    plotter.view_vector(view_vector, up_vector)

    plotter.screenshot(output_png, transparent_background=False)
    plotter.close()
    print(f"  Rendered map {map_id} → {output_png}")


def compose_figure(panel_pngs):
    """Compose PyVista renders into Economist-style figure."""

    fig = plt.figure(figsize=(7.5, 4.0), facecolor=BG_WHITE)

    # Red top line
    fig.patches.append(
        FancyBboxPatch(
            (0.02, 0.945),
            0.96,
            0.012,
            transform=fig.transFigure,
            facecolor=RED,
            edgecolor="none",
            clip_on=False,
            boxstyle="square,pad=0",
        )
    )

    fig.text(
        0.025,
        0.915,
        "Wo der Algorithmus scharf sieht — und wo nicht",
        fontsize=12,
        fontweight="bold",
        color=GRAY_DARK,
        va="top",
    )
    fig.text(
        0.025,
        0.87,
        "Matching-Score-Verteilung auf der Vorhofoberfläche. Kreuz = Vertex mit höchstem Score.",
        fontsize=8,
        color=GRAY_MID,
        va="top",
        fontstyle="italic",
    )

    gs = fig.add_gridspec(
        1,
        4,
        width_ratios=[1, 1, 1, 0.05],
        left=0.03,
        right=0.97,
        bottom=0.05,
        top=0.81,
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

        # Economist-style annotations
        ax.text(
            -0.06,
            1.08,
            panel["letter"],
            transform=ax.transAxes,
            fontsize=16,
            fontweight="bold",
            color=GRAY_DARK,
            va="top",
        )
        ax.text(
            0.04,
            1.07,
            panel["title"],
            transform=ax.transAxes,
            fontsize=9.5,
            fontweight="bold",
            color=GRAY_DARK,
            va="top",
        )
        ax.text(
            0.04,
            0.975,
            panel["subtitle"],
            transform=ax.transAxes,
            fontsize=7.5,
            color=GRAY_MID,
            va="top",
            fontstyle="italic",
        )

        box_text = f"σ = {panel['sigma']} mm\n$A_{{≥θ}}$ = {panel['area']} cm²"
        ax.text(
            0.97,
            0.04,
            box_text,
            transform=ax.transAxes,
            fontsize=6.5,
            color="#D5D8DC",
            va="bottom",
            ha="right",
            fontfamily="Source Code Pro",
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
    sm = plt.cm.ScalarMappable(cmap=econ_cmap, norm=plt.Normalize(vmin=50, vmax=100))
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax)
    cb.set_label("Matching-Score (%)", fontsize=7.5, color=GRAY_DARK)
    cb.ax.tick_params(labelsize=6, colors=GRAY_MID)
    cb.outline.set_linewidth(0.4)
    cb.outline.set_edgecolor(GRAY_LIGHT)

    # Source line
    fig.text(
        0.025,
        0.008,
        "Quelle: Eigene Daten, Messung CARTO-3-System, Plot pulse-ultimate · UKSH Kiel",
        fontsize=6,
        color=GRAY_MID,
        va="bottom",
        fontfamily="Source Code Pro",
    )

    fig.savefig(OUTPATH, dpi=200)
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

    print("\nComposing Economist-style figure...")
    compose_figure(panel_pngs)
