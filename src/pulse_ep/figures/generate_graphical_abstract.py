#!/usr/bin/env python3
"""
Graphical Abstract — Clinical Paper (Europace)

PyVista 3D rendering of RA lateral (SC vs DC) + σ boxplot.
Uses the same rendering pipeline as generate_heatmap_clinical.py.

Layout:
  ┌──────────────────────────────────────────────────────┐
  │  Title: key message                                  │
  ├──────────────┬────────┬──────────────┬───┬───────────┤
  │  RA lat SC   │   →    │  RA lat DC   │ c │  σ boxplot│
  │  (diffuse)   │ +RA    │  (focal)     │ b │  RA lat   │
  │  3D PyVista  │ cath.  │  3D PyVista  │ a │  SC vs DC │
  ├──────────────┴────────┴──────────────┴───┴───────────┤
  │  Bottom: take-home message                           │
  └──────────────────────────────────────────────────────┘

Styles:
  --style journal    Clean white background (default, for Europace submission)
  --style economist  Cream background, red top bar, Economist typography

Requires: pulse_ep (database access), pyvista, matplotlib, scipy, pandas
Run from pulse-ultimate root with venv active:
    python generate_graphical_abstract.py
    python generate_graphical_abstract.py --style economist

Output: thesis-med/_paper/clinical-paper/figs/graphical_abstract.pdf
"""

import matplotlib

matplotlib.use("Agg")
import argparse
import os

import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvista as pv
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch
from scipy.optimize import curve_fit
from scipy.spatial import cKDTree

from pulse_ep.core import plot_proc as plot_proc
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel, EPMapPoint

DISTANCE_THRESHOLD = 8  # mm

# ─── Paths ─────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "decay_profiles_heat")
REPORT_DIR = os.path.join(SCRIPT_DIR, "reports")
OUTDIR = os.path.join(SCRIPT_DIR, "..", "thesis-med", "_paper", "clinical-paper", "figs")
OUTDIR = os.path.normpath(OUTDIR)
TMP_DIR = "/tmp/graphical_abstract_panels"

# ─── CLI ───────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Generate graphical abstract for clinical paper.")
parser.add_argument(
    "--style",
    choices=["journal", "economist"],
    default="journal",
    help="Visual style (default: journal)",
)
args = parser.parse_args()
STYLE = args.style

# ─── Register user fonts ──────────────────────────────────
for fontdir in [os.path.expanduser("~/Library/Fonts"), "/usr/share/fonts"]:
    if os.path.isdir(fontdir):
        for f in fm.findSystemFonts(fontpaths=[fontdir]):
            try:
                fm.fontManager.addfont(f)
            except:  # noqa: E722
                pass


# ═══════════════════════════════════════════════════════════
# STYLE DEFINITIONS
# ═══════════════════════════════════════════════════════════

# Shared colours
TEAL = "#00857C"
AMBER = "#D4950A"  # SC catheter config
SLATE = "#2D6A4F"  # DC catheter config

if STYLE == "economist":
    ECON_RED = "#E3120B"
    BLUE = "#006BA6"
    RED = "#B2182B"
    GRAY_DARK = "#333333"
    GRAY_MID = "#76787A"
    GRAY_LIGHT = "#D9D9D9"
    BG = "#F7F5F0"  # cream
    PANEL_BG = "#1C2833"
    TITLE_COLOR = GRAY_DARK
    SUBTITLE_COLOR = GRAY_MID
    BOX_BG = "#EBE8E1"  # slightly darker cream for message box

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Source Sans 3",
                "Source Sans Pro",
                "Helvetica Neue",
                "DejaVu Sans",
            ],
            "font.size": 9,
            "axes.facecolor": BG,
            "axes.edgecolor": GRAY_LIGHT,
            "axes.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRAY_LIGHT,
            "grid.linewidth": 0.4,
            "grid.alpha": 0.6,
            "xtick.color": GRAY_MID,
            "ytick.color": GRAY_MID,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "figure.facecolor": BG,
            "figure.dpi": 300,
            "savefig.facecolor": BG,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.15,
        }
    )

else:  # journal (default)
    BLUE = "#2166AC"
    RED = "#B2182B"
    GRAY_DARK = "#333333"
    GRAY_MID = "#76787A"
    GRAY_LIGHT = "#D9D9D9"
    BG = "#FFFFFF"
    PANEL_BG = "#1C2833"
    TITLE_COLOR = GRAY_DARK
    SUBTITLE_COLOR = GRAY_MID
    BOX_BG = "#F0F4F8"

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Source Sans 3",
                "Source Sans Pro",
                "Helvetica Neue",
                "DejaVu Sans",
            ],
            "font.size": 9,
            "axes.facecolor": BG,
            "axes.edgecolor": GRAY_LIGHT,
            "axes.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRAY_LIGHT,
            "grid.linewidth": 0.4,
            "grid.alpha": 0.6,
            "xtick.color": GRAY_MID,
            "ytick.color": GRAY_MID,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "figure.facecolor": BG,
            "figure.dpi": 300,
            "savefig.facecolor": BG,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.12,
        }
    )


# ─── Panels ────────────────────────────────────────────────
PANELS = [
    {
        "map_id": 78,
        "label": "Single-chamber reference",
        "label_color": BLUE,
        "sigma": "36.2",
        "r2": "0.86",
        "atrium": "RA",
        "direction": "RL",
    },
    {
        "map_id": 25,
        "label": "Double-chamber reference",
        "label_color": RED,
        "sigma": "4.7",
        "r2": "0.98",
        "atrium": "RA",
        "direction": "RL",
    },
]

# ─── Colormap for matplotlib colorbar ──────────────────────
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


# ═══════════════════════════════════════════════════════════
# PyVista RENDERING (same as generate_heatmap_clinical.py)
# ═══════════════════════════════════════════════════════════


def render_panel(session, panel_info, output_png):
    """Render a single mesh panel using PyVista."""
    map_id = panel_info["map_id"]

    epmap_model = EPMapModel.find_by_id(map_id, session)
    if epmap_model is None:
        raise ValueError(f"Map {map_id} not found")

    vertices = np.array(epmap_model.vertices).reshape(-1, 3)
    triangles = np.array(epmap_model.triangles).reshape(-1, 3)
    act_bip = np.array(epmap_model.act_bip).reshape(-1, 2)

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

    faces_pv = np.pad(triangles, ((0, 0), (1, 0)), "constant", constant_values=3)
    pv_mesh = pv.PolyData(vertices, faces_pv)

    scalar_data = act_bip[:, 0].copy()
    if np.nanmax(scalar_data) < 0:
        scalar_data = -scalar_data
    max_val = np.nanmax(scalar_data)
    if max_val != 0:
        scalar_data = (scalar_data / max_val) * 100

    tree = cKDTree(point_xyz)
    distances, _ = tree.query(vertices)
    far_mask = distances > DISTANCE_THRESHOLD
    scalar_data[far_mask] = np.nan

    pv_mesh.point_data["act"] = scalar_data
    cmap = plot_proc.create_modified_hsv_colormap()
    clim = [50, 100]

    direction = panel_info["direction"]
    atrium = panel_info["atrium"]

    if direction == "PA":
        view_vector = np.array([0, 0, -1])
        up_vector = np.array([0, 1, 0])
    elif direction == "RL":
        if atrium == "RA":
            view_vector = np.array([1, 0, 0])
            up_vector = np.array([1, 1, 0])
        else:
            view_vector = np.array([-1, 0, 0])
            up_vector = np.array([0, 0, -1])

    plotter = pv.Plotter(window_size=(1200, 1000), off_screen=True)
    plotter.set_background(PANEL_BG)
    plotter.add_mesh(
        pv_mesh,
        scalars="act",
        cmap=cmap,
        clim=clim,
        show_scalar_bar=False,
        nan_color="#BDBDBD",
        nan_opacity=0.4,
    )

    valid_mask = ~np.isnan(scalar_data)
    if valid_mask.any():
        origin_idx = np.nanargmax(scalar_data)
        origin_pt = vertices[origin_idx].copy()
        pv_mesh.compute_normals(cell_normals=False, point_normals=True, inplace=True)
        normal = pv_mesh.point_normals[origin_idx]
        origin_pt_offset = origin_pt + normal * 2.0
        origin_mesh = pv.PolyData(origin_pt_offset.reshape(1, 3))
        plotter.add_mesh(
            origin_mesh, color="white", point_size=18, render_points_as_spheres=True, style="points"
        )

    plotter.view_vector(view_vector, up_vector)
    plotter.screenshot(output_png, transparent_background=False)
    plotter.close()
    print(f"  Rendered → {output_png}")


# ═══════════════════════════════════════════════════════════
# BOXPLOT DATA (Gaussian fits for all RA lateral maps)
# ═══════════════════════════════════════════════════════════


def gauss(d, A, sigma, B):
    return A * np.exp(-(d**2) / (2 * sigma**2)) + B


def fit_map(map_id, bin_width=2):
    fp = os.path.join(DATA_DIR, f"decay_map_{map_id:03d}.csv")
    if not os.path.exists(fp):
        return None
    p = pd.read_csv(fp)
    dist = p["geodesic_dist_mm"]
    max_dist = dist.max()
    if max_dist < 5:
        return None
    bins = np.arange(0, max_dist + bin_width, bin_width)
    p["bin"] = pd.cut(dist, bins, labels=False)
    binned = p.groupby("bin")["matching_score_pct"].mean().dropna()
    d_centers = (binned.index * bin_width + bin_width / 2).values.astype(float)
    scores = binned.values
    if len(scores) < 3:
        return None
    try:
        A0 = scores.max() - scores.min()
        popt, _ = curve_fit(
            gauss,
            d_centers,
            scores,
            p0=[A0, 10.0, scores.min()],
            bounds=([0, 0.1, -np.inf], [np.inf, 200.0, np.inf]),
            maxfev=5000,
        )
        return popt[1]  # sigma
    except:  # noqa: E722
        return None


def load_boxplot_data():
    """Load sigma values for all RA lateral maps, split by SC/DC."""
    report_path = os.path.join(REPORT_DIR, "2_Pacemapping_5.xlsx")
    xls = pd.read_excel(report_path, sheet_name="Sheet1")
    ra_lat = xls[
        (xls["part"].str.contains("lateral", case=False, na=False)) & (xls["pacemap"] == True)  # noqa: E712
    ].copy()

    sigma_sc, sigma_dc = [], []
    for _, row in ra_lat.iterrows():
        mid = int(row["ID"])
        ref_elec = int(row["reference_electrodes"])
        sigma = fit_map(mid)
        if sigma is not None:
            if ref_elec == 2:
                sigma_dc.append(sigma)
            else:
                sigma_sc.append(sigma)

    print(
        f"  SC (n={len(sigma_sc)}): median {np.median(sigma_sc):.1f} mm"
        if sigma_sc
        else "  SC: no data"
    )
    print(
        f"  DC (n={len(sigma_dc)}): median {np.median(sigma_dc):.1f} mm"
        if sigma_dc
        else "  DC: no data"
    )
    return sigma_sc, sigma_dc


# ═══════════════════════════════════════════════════════════
# COMPOSE GRAPHICAL ABSTRACT
# ═══════════════════════════════════════════════════════════


def compose(panel_pngs, sigma_sc, sigma_dc):
    """Compose catheter schematics + PyVista panels + boxplot."""

    # Catheter schematic PNGs
    FIGS_DIR = os.path.join(SCRIPT_DIR, "..", "thesis-med", "_paper", "clinical-paper", "figs")
    if STYLE == "economist":
        sc_schema_path = os.path.normpath(os.path.join(FIGS_DIR, "sc_economist.png"))
        dc_schema_path = os.path.normpath(os.path.join(FIGS_DIR, "dc_economist.png"))
    else:
        sc_schema_path = os.path.normpath(os.path.join(FIGS_DIR, "sc.png"))
        dc_schema_path = os.path.normpath(os.path.join(FIGS_DIR, "dc.png"))

    fig = plt.figure(figsize=(7.5, 5.2), facecolor=BG)

    # 2 rows × 4 cols: [schema | arrow | heatmap | boxplot]
    gs = fig.add_gridspec(
        2,
        4,
        width_ratios=[0.8, 0.10, 1, 0.55],
        height_ratios=[1, 1],
        left=0.03,
        right=0.97,
        bottom=0.14,
        top=0.82,
        wspace=0.04,
        hspace=0.08,
    )

    ax_sc_schema = fig.add_subplot(gs[0, 0])  # SC anatomy
    ax_sc_heat = fig.add_subplot(gs[0, 2])  # SC heatmap
    ax_dc_schema = fig.add_subplot(gs[1, 0])  # DC anatomy
    ax_dc_heat = fig.add_subplot(gs[1, 2])  # DC heatmap
    ax_box = fig.add_subplot(gs[:, 3])  # boxplot spans both rows, right

    # ── Economist: red top bar ─────────────────────────────
    if STYLE == "economist":
        fig.patches.append(
            FancyBboxPatch(
                (0.02, 0.985),
                0.96,
                0.012,
                transform=fig.transFigure,
                facecolor=ECON_RED,
                edgecolor="none",
                clip_on=False,
                boxstyle="square,pad=0",
            )
        )

    # ── Title ──────────────────────────────────────────────
    title_y = 0.96 if STYLE == "economist" else 0.98
    fig.text(
        0.50,
        title_y,
        "How Precise Is Atrial Pace Mapping and Can It Be Improved?",
        fontsize=13 if STYLE == "economist" else 12.5,
        fontweight="bold",
        color=TITLE_COLOR,
        ha="center",
        va="top",
        linespacing=1.25,
    )

    subtitle_y = title_y - 0.045
    fig.text(
        0.50,
        subtitle_y,
        "Double-chamber reference reduces σ from up to 25 mm to 5 mm across all atrial regions",
        fontsize=9 if STYLE == "economist" else 8.5,
        color=SUBTITLE_COLOR,
        ha="center",
        va="top",
        fontstyle="italic",
    )

    # ── Row labels (left of schematics) ──────────────────────
    sc_schema_pos = ax_sc_schema.get_position()
    dc_schema_pos = ax_dc_schema.get_position()

    sc_row_mid = sc_schema_pos.y0 + sc_schema_pos.height / 2  # noqa: F841
    dc_row_mid = dc_schema_pos.y0 + dc_schema_pos.height / 2  # noqa: F841

    fig.text(
        sc_schema_pos.x0 + sc_schema_pos.width / 2,
        sc_schema_pos.y1 + 0.015,
        PANELS[0]["label"],
        fontsize=8,
        fontweight="bold",
        color=AMBER,
        ha="center",
        va="bottom",
        transform=fig.transFigure,
    )
    fig.text(
        dc_schema_pos.x0 + dc_schema_pos.width / 2,
        dc_schema_pos.y1 + 0.015,
        PANELS[1]["label"],
        fontsize=8,
        fontweight="bold",
        color=SLATE,
        ha="center",
        va="bottom",
        transform=fig.transFigure,
    )

    # ── Catheter schematics (left column) ──────────────────
    for ax, schema_path in [(ax_sc_schema, sc_schema_path), (ax_dc_schema, dc_schema_path)]:
        img = mpimg.imread(schema_path)
        ax.imshow(img)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_facecolor(BG)

    # ── Arrows between schema → heatmap (per row) ─────────
    arrow_colors = [AMBER, SLATE]
    # Use a hidden axes spanning the full figure for arrow annotations
    ax_arrow = fig.add_axes([0, 0, 1, 1], facecolor="none")
    ax_arrow.set_xlim(0, 1)
    ax_arrow.set_ylim(0, 1)
    ax_arrow.axis("off")

    for (schema_ax, heat_ax), acol in zip(  # noqa: B905
        [(ax_sc_schema, ax_sc_heat), (ax_dc_schema, ax_dc_heat)], arrow_colors
    ):
        s_pos = schema_ax.get_position()
        h_pos = heat_ax.get_position()
        arrow_x_start = s_pos.x1 + 0.005
        arrow_x_end = h_pos.x0 - 0.005
        arrow_y = s_pos.y0 + s_pos.height / 2
        ax_arrow.annotate(
            "",
            xy=(arrow_x_end, arrow_y),
            xytext=(arrow_x_start, arrow_y),
            arrowprops=dict(arrowstyle="-|>", color=acol, lw=2.5, mutation_scale=18),
        )

    # ── PyVista heatmaps (middle column) ───────────────────
    for ax, png_path, panel in zip([ax_sc_heat, ax_dc_heat], panel_pngs, PANELS):  # noqa: B905
        img = mpimg.imread(png_path)
        ax.imshow(img)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#2C3E50")
            spine.set_linewidth(0.6)

        # σ / R² box inside panel
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
                facecolor=PANEL_BG,
                edgecolor="#2C3E50",
                linewidth=0.5,
                alpha=0.88,
            ),
        )

    # ── Annotation arrows on heatmaps ────────────────────────
    # SC: large diffuse region — arrow tip ends at edge of colored area
    ax_sc_heat.annotate(
        "diffuse",
        xy=(0.42, 0.50),
        xycoords="axes fraction",  # edge of colored region
        xytext=(0.12, 0.88),
        textcoords="axes fraction",  # label top-left
        fontsize=7,
        color="white",
        fontweight="bold",
        ha="center",
        va="center",
        arrowprops=dict(
            arrowstyle="-|>",
            color="white",
            lw=1.2,
            connectionstyle="arc3,rad=0.15",
            mutation_scale=12,
        ),
    )

    # DC: small focal region — arrow tip ends at edge of colored area
    ax_dc_heat.annotate(
        "focal",
        xy=(0.45, 0.52),
        xycoords="axes fraction",  # edge of colored region
        xytext=(0.12, 0.88),
        textcoords="axes fraction",  # label top-left
        fontsize=7,
        color="white",
        fontweight="bold",
        ha="center",
        va="center",
        arrowprops=dict(
            arrowstyle="-|>",
            color="white",
            lw=1.2,
            connectionstyle="arc3,rad=0.15",
            mutation_scale=12,
        ),
    )

    # ── Colorbar (small inset inside each heatmap) ───────────
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    gradient = np.linspace(0, 1, 256).reshape(-1, 1)

    for heat_ax in [ax_sc_heat, ax_dc_heat]:
        cax = inset_axes(heat_ax, width="5%", height="45%", loc="lower left", borderpad=1.2)
        cax.set_facecolor("none")
        cax.imshow(gradient, aspect="auto", cmap=cbar_cmap, origin="lower", extent=[0, 1, 50, 100])
        cax.set_xlim(0, 1)
        cax.set_ylim(50, 100)
        cax.set_xticks([])
        cax.set_yticks([50, 75, 100])
        cax.tick_params(
            labelsize=4.5,
            colors="#D5D8DC",
            pad=1,
            length=2,
            left=False,
            right=True,
            labelleft=False,
            labelright=True,
        )
        cax.set_ylabel("Score %", fontsize=5, color="#D5D8DC", labelpad=2)
        cax.yaxis.set_label_position("right")
        for spine in cax.spines.values():
            spine.set_linewidth(0.4)
            spine.set_edgecolor("#2C3E50")

    # ── Boxplot: σ for RA lateral ──────────────────────────
    ax_box.grid(False)
    ax_box.set_axisbelow(True)

    if sigma_sc and sigma_dc:
        bp_data = [sigma_sc, sigma_dc]
        bp = ax_box.boxplot(
            bp_data, positions=[1, 2], widths=0.5, patch_artist=True, showfliers=False
        )

        box_colors = [AMBER, SLATE]  # SC=amber, DC=slate
        for patch, fc in zip(bp["boxes"], box_colors):  # noqa: B905
            patch.set_facecolor(fc)
            patch.set_alpha(0.3)
            patch.set_edgecolor(fc)
            patch.set_linewidth(1.4)
        for element in ["whiskers", "caps"]:
            for i, line in enumerate(bp[element]):
                line.set_color(box_colors[i // 2])
                line.set_linewidth(1.0)
        for i, line in enumerate(bp["medians"]):
            line.set_color(box_colors[i])
            line.set_linewidth(2.0)

        # Individual data points
        for i, (data, color) in enumerate(zip(bp_data, box_colors)):  # noqa: B905
            jitter = np.random.default_rng(42).normal(0, 0.06, len(data))
            ax_box.scatter(
                [i + 1] * len(data) + jitter,
                data,
                s=16,
                c=color,
                alpha=0.6,
                zorder=5,
                edgecolors="none",
            )

        y_max = max(max(sigma_sc), max(sigma_dc))

        ax_box.set_xticks([1, 2])
        ax_box.set_xticklabels(["SC", "DC"], fontsize=8, fontweight="bold")
        for label, color in zip(ax_box.get_xticklabels(), [AMBER, SLATE]):  # noqa: B905
            label.set_color(color)
        ax_box.set_ylabel("σ (mm)", fontsize=8, color=GRAY_DARK)
        ax_box.yaxis.set_label_position("right")
        ax_box.yaxis.tick_right()
        ax_box.set_title("RA lateral wall", fontsize=9, fontweight="bold", color=GRAY_DARK, pad=6)
        ax_box.set_ylim(bottom=0, top=y_max * 1.1)

        # Clean spines
        ax_box.spines["top"].set_visible(False)
        ax_box.spines["left"].set_visible(False)
    else:
        ax_box.text(
            0.5,
            0.5,
            "No data",
            transform=ax_box.transAxes,
            ha="center",
            va="center",
            fontsize=8,
            color=GRAY_MID,
        )

    # ── Bottom message (key claim) ───────────────────────────
    fig.text(
        0.50,
        0.06,
        "DC reference improves resolution across all atrial regions "
        "(4–6 mm, comparable to ventricular\n"
        "pace mapping; Azegami et al., 2005), "
        "with the largest effect on the RA lateral wall",
        fontsize=9.5,
        fontweight="bold",
        color=GRAY_DARK,
        ha="center",
        va="center",
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.5", facecolor=BOX_BG, edgecolor=GRAY_MID, linewidth=1.0),
    )

    # ── Economist: source line ─────────────────────────────
    if STYLE == "economist":
        fig.text(
            0.03,
            0.005,
            "Source: own data, CARTO-3 system · UKSH Kiel",
            fontsize=6,
            color=GRAY_MID,
            va="bottom",
            fontfamily="monospace",
        )

    # ── Save ───────────────────────────────────────────────
    os.makedirs(OUTDIR, exist_ok=True)
    suffix = f"_{STYLE}" if STYLE != "journal" else ""
    for ext in ["pdf", "png"]:
        outpath = os.path.join(OUTDIR, f"graphical_abstract{suffix}.{ext}")
        fig.savefig(outpath, dpi=300)
        print(f"  ✓ {outpath}")
    plt.close()


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(TMP_DIR, exist_ok=True)

    print(f"Style: {STYLE}")
    print("Rendering mesh panels via PyVista...")
    panel_pngs = []
    with get_db_session() as session:
        for panel in PANELS:
            png_path = os.path.join(TMP_DIR, f"panel_{panel['map_id']}.png")
            render_panel(session, panel, png_path)
            panel_pngs.append(png_path)

    print("\nLoading σ values for RA lateral boxplot...")
    sigma_sc, sigma_dc = load_boxplot_data()

    print("\nComposing graphical abstract...")
    compose(panel_pngs, sigma_sc, sigma_dc)
