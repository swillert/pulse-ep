#!/usr/bin/env python3
"""
Geodäsik-Vergleich: Dijkstra vs. Heat Method auf allen Pacemap-Meshes.

Berechnet für jede Pacemap:
  1. Dijkstra-Distanzen (bestehende Pipeline)
  2. Heat-Method-Distanzen (exakte Geodäten via potpourri3d)
  3. Vergleich: relativer Fehler, σ-Differenz nach Gauß-Fit
  4. Optional: Re-Fit der klinischen Daten mit Heat-Method-Distanzen

Ergebnisse:
  decay_profiles/geodesic_comparison.csv       — pro Map: σ_dijkstra, σ_heat, Fehlerstatistik
  decay_profiles/geodesic_error_by_distance.csv — relativer Fehler als Funktion der Distanz
  decay_profiles/meshes/mesh_XXX.npz           — extrahierte Meshes (für Offline-Analyse)

Voraussetzungen:
  pip install potpourri3d   (nutzt geometry-central C++ für Heat Method)

Nutzung:
  cd /path/to/pulse-ultimate
  python3 geodesic_comparison.py              # Voller Lauf
  python3 geodesic_comparison.py --plot       # + Abbildungen
  python3 geodesic_comparison.py --export-meshes  # auch .npz speichern
"""

import os
import csv
import argparse
import numpy as np
from scipy.optimize import curve_fit

# Bestehende Pipeline
from spatial_decay import build_adjacency_matrix, compute_geodesic_distances

# Heat Method Solver
import potpourri3d as pp3d

# DB-Zugang
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel, EPMapAttributes

OUTPUT_DIR = './decay_profiles'
MESH_DIR = os.path.join(OUTPUT_DIR, 'meshes')

# Gauß-Fit-Parameter (identisch mit validate_sigma.py)
BIN_WIDTH = 2       # mm
SIGMA_UPPER = 200   # mm — generous upper bound for σ (matching clinical pipeline)
SIGMA_BOUNDS = (0.1, 200.0)


def gauss(d, A, sigma, B):
    """Gauß-Funktion."""
    return A * np.exp(-d**2 / (2 * sigma**2)) + B


def compute_heat_distances(vertices, triangles, origin_idx):
    """Compute geodesic distances using the Heat Method (Crane et al. 2017).

    Uses potpourri3d which wraps geometry-central C++.
    Returns distances array of shape (n_vertices,).
    """
    faces = np.asarray(triangles, dtype=np.int64)
    verts = np.asarray(vertices, dtype=np.float64)
    solver = pp3d.MeshHeatMethodDistanceSolver(verts, faces)
    return solver.compute_distance(origin_idx)


def fit_decay_profile(distances, scores, bin_width=BIN_WIDTH):
    """Bin + Gauß-Fit. Uses full mesh distance for binning (matching clinical pipeline).
    Returns dict or None."""
    valid = np.isfinite(distances) & ~np.isnan(scores)
    d_valid = distances[valid]
    s_valid = scores[valid]

    if len(d_valid) < 10:
        return None

    max_dist = d_valid.max() if len(d_valid) > 0 else 0
    bins = np.arange(0, max_dist + bin_width, bin_width)
    bin_idx = np.digitize(d_valid, bins) - 1
    n_bins_total = len(bins) - 1

    bin_means = np.full(n_bins_total, np.nan)
    for k in range(n_bins_total):
        mask = bin_idx == k
        if np.sum(mask) >= 3:
            bin_means[k] = np.mean(s_valid[mask])

    valid_bins = ~np.isnan(bin_means)
    if np.sum(valid_bins) < 4:
        return None

    d_centers = (np.arange(n_bins_total) + 0.5) * bin_width
    d_fit = d_centers[valid_bins]
    s_fit = bin_means[valid_bins]

    try:
        A0 = s_fit.max() - s_fit.min()
        B0 = s_fit.min()
        popt, _ = curve_fit(
            gauss, d_fit, s_fit,
            p0=[A0, 10.0, B0],
            bounds=([0, SIGMA_BOUNDS[0], -np.inf],
                    [np.inf, SIGMA_BOUNDS[1], np.inf]),
            maxfev=5000
        )
        A_hat, sigma_hat, B_hat = popt
        ss_res = np.sum((s_fit - gauss(d_fit, *popt))**2)
        ss_tot = np.sum((s_fit - np.mean(s_fit))**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return {'sigma': abs(sigma_hat), 'A': A_hat, 'B': B_hat,
                'r_squared': r_squared, 'n_bins': int(np.sum(valid_bins))}
    except (RuntimeError, ValueError):
        return None


def compute_distance_binned_errors(dijkstra_dists, heat_dists, bin_width=2.0, max_dist=60.0):
    """Compute relative error binned by geodesic distance."""
    valid = np.isfinite(dijkstra_dists) & np.isfinite(heat_dists) & (heat_dists > 0.1)
    d_heat = heat_dists[valid]
    d_dijk = dijkstra_dists[valid]
    rel_err = (d_dijk - d_heat) / d_heat

    bins = np.arange(0, max_dist + bin_width, bin_width)
    bin_idx = np.digitize(d_heat, bins) - 1
    n_bins = len(bins) - 1

    rows = []
    for k in range(n_bins):
        mask = bin_idx == k
        n = np.sum(mask)
        if n >= 5:
            errs = rel_err[mask]
            rows.append({
                'dist_center_mm': (k + 0.5) * bin_width,
                'n_vertices': int(n),
                'mean_rel_error': float(np.mean(errs)),
                'median_rel_error': float(np.median(errs)),
                'std_rel_error': float(np.std(errs)),
                'p5_rel_error': float(np.percentile(errs, 5)),
                'p95_rel_error': float(np.percentile(errs, 95)),
            })
    return rows


def run_comparison(export_meshes=False):
    """Main comparison: Dijkstra vs Heat Method on all pacemaps."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if export_meshes:
        os.makedirs(MESH_DIR, exist_ok=True)

    summary_rows = []
    all_error_rows = []

    with get_db_session() as session:
        # Load all pacemaps with atrium + part set
        pacemap_entries = (
            session.query(EPMapModel, EPMapAttributes)
            .join(EPMapAttributes, EPMapAttributes.map_id == EPMapModel.id)
            .filter(EPMapAttributes.attributes['pacemap'].astext.cast(
                __import__('sqlalchemy').Boolean) == True)
            .all()
        )

        filtered = []
        for epmap, attrs in pacemap_entries:
            a = attrs.attributes or {}
            atrium = a.get('atrium', '')
            part = a.get('part', '')
            if atrium and part:
                filtered.append((epmap, attrs))

        print(f"Found {len(filtered)} pacemaps with atrium + part set.\n")

        for epmap, attrs in filtered:
            map_id = epmap.id
            map_name = epmap.map_name
            a = attrs.attributes or {}
            atrium = a.get('atrium', '')
            part = a.get('part', '')
            ref_catheters = a.get('reference_electrodes', 0)

            # Load mesh
            vertices = np.array(epmap.vertices).reshape(-1, 3)
            triangles = np.array(epmap.triangles).reshape(-1, 3)
            act_bip = np.array(epmap.act_bip).reshape(-1, 2)
            n_verts = len(vertices)

            print(f"Map {map_id:>3}: {map_name:<45} ({n_verts:>6} verts)", end="  ")

            # Export mesh if requested
            if export_meshes:
                np.savez_compressed(
                    os.path.join(MESH_DIR, f'mesh_{map_id:03d}.npz'),
                    vertices=vertices, triangles=triangles, act_bip=act_bip
                )

            # Matching score + origin
            matching_score = np.abs(act_bip[:, 0])
            score_clean = np.where(np.isnan(matching_score), 0.0, matching_score)
            origin_idx = int(np.argmax(score_clean))

            # ── Dijkstra distances ──
            adj = build_adjacency_matrix(vertices, triangles)
            dijk_dists = compute_geodesic_distances(adj, origin_idx)

            # ── Heat Method distances ──
            try:
                heat_dists = compute_heat_distances(vertices, triangles, origin_idx)
            except Exception as e:
                print(f"⚠ Heat Method failed: {e}")
                summary_rows.append({
                    'map_id': map_id, 'map_name': map_name,
                    'atrium': atrium, 'part': part, 'ref_catheters': ref_catheters,
                    'n_vertices': n_verts, 'error': str(e),
                })
                continue

            # ── Compare distances ──
            both_finite = np.isfinite(dijk_dists) & np.isfinite(heat_dists) & (heat_dists > 0.1)
            rel_errors = (dijk_dists[both_finite] - heat_dists[both_finite]) / heat_dists[both_finite]
            abs_errors = dijk_dists[both_finite] - heat_dists[both_finite]

            mean_rel_err = float(np.mean(rel_errors)) * 100
            median_rel_err = float(np.median(rel_errors)) * 100
            max_rel_err = float(np.max(rel_errors)) * 100
            mean_abs_err = float(np.mean(abs_errors))

            # Mean edge length
            edge_lengths = []
            for tri in triangles:
                for i in range(3):
                    v0, v1 = tri[i], tri[(i + 1) % 3]
                    edge_lengths.append(np.linalg.norm(vertices[v0] - vertices[v1]))
            mean_edge = float(np.mean(edge_lengths))

            # ── Gauß-Fit with both distance methods ──
            fit_dijk = fit_decay_profile(dijk_dists, matching_score)
            fit_heat = fit_decay_profile(heat_dists, matching_score)

            sigma_dijk = fit_dijk['sigma'] if fit_dijk else np.nan
            sigma_heat = fit_heat['sigma'] if fit_heat else np.nan
            sigma_diff = sigma_dijk - sigma_heat if (fit_dijk and fit_heat) else np.nan

            r2_dijk = fit_dijk['r_squared'] if fit_dijk else np.nan
            r2_heat = fit_heat['r_squared'] if fit_heat else np.nan

            status = "✓" if fit_dijk and fit_heat else "⚠"
            print(f"{status} σ_dijk={sigma_dijk:5.1f}  σ_heat={sigma_heat:5.1f}  "
                  f"Δσ={sigma_diff:+5.2f} mm  "
                  f"rel_err={mean_rel_err:+.1f}%  edge={mean_edge:.1f}mm")

            summary_rows.append({
                'map_id': map_id,
                'map_name': map_name,
                'atrium': atrium,
                'part': part,
                'ref_catheters': ref_catheters,
                'n_vertices': n_verts,
                'mean_edge_mm': round(mean_edge, 2),
                'origin_idx': origin_idx,
                'n_finite_both': int(np.sum(both_finite)),
                'mean_rel_error_pct': round(mean_rel_err, 3),
                'median_rel_error_pct': round(median_rel_err, 3),
                'max_rel_error_pct': round(max_rel_err, 3),
                'mean_abs_error_mm': round(mean_abs_err, 3),
                'sigma_dijkstra': round(sigma_dijk, 3) if np.isfinite(sigma_dijk) else '',
                'sigma_heat': round(sigma_heat, 3) if np.isfinite(sigma_heat) else '',
                'sigma_diff_mm': round(sigma_diff, 3) if np.isfinite(sigma_diff) else '',
                'r2_dijkstra': round(r2_dijk, 4) if np.isfinite(r2_dijk) else '',
                'r2_heat': round(r2_heat, 4) if np.isfinite(r2_heat) else '',
            })

            # Binned error profile
            err_rows = compute_distance_binned_errors(dijk_dists, heat_dists)
            for row in err_rows:
                row['map_id'] = map_id
                row['mean_edge_mm'] = round(mean_edge, 2)
                row['n_vertices'] = n_verts
            all_error_rows.extend(err_rows)

    # ── Save summary ──
    summary_path = os.path.join(OUTPUT_DIR, 'geodesic_comparison.csv')
    fieldnames = [
        'map_id', 'map_name', 'atrium', 'part', 'ref_catheters',
        'n_vertices', 'mean_edge_mm', 'origin_idx', 'n_finite_both',
        'mean_rel_error_pct', 'median_rel_error_pct', 'max_rel_error_pct',
        'mean_abs_error_mm',
        'sigma_dijkstra', 'sigma_heat', 'sigma_diff_mm',
        'r2_dijkstra', 'r2_heat',
    ]
    with open(summary_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"\nSummary: {summary_path}")

    # ── Save error-by-distance profile ──
    if all_error_rows:
        err_path = os.path.join(OUTPUT_DIR, 'geodesic_error_by_distance.csv')
        err_fields = ['map_id', 'n_vertices', 'mean_edge_mm', 'dist_center_mm',
                       'n_vertices', 'mean_rel_error', 'median_rel_error',
                       'std_rel_error', 'p5_rel_error', 'p95_rel_error']
        with open(err_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(all_error_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_error_rows)
        print(f"Error profile: {err_path}")

    return summary_rows, all_error_rows


def print_summary(summary_rows):
    """Print aggregate statistics."""
    valid = [r for r in summary_rows if 'sigma_dijkstra' in r and r.get('sigma_dijkstra')]

    if not valid:
        print("No valid results.")
        return

    sigma_diffs = [float(r['sigma_diff_mm']) for r in valid if r.get('sigma_diff_mm')]
    rel_errors = [float(r['mean_rel_error_pct']) for r in valid if r.get('mean_rel_error_pct')]
    mean_edges = [float(r['mean_edge_mm']) for r in valid]

    print(f"\n{'='*70}")
    print("ZUSAMMENFASSUNG: Dijkstra vs. Heat Method")
    print(f"{'='*70}")
    print(f"  Analysierte Maps:           {len(valid)}")
    print(f"  Mittlere Kantenlänge:       {np.mean(mean_edges):.2f} mm "
          f"(Range: {np.min(mean_edges):.2f}–{np.max(mean_edges):.2f})")
    print(f"\n  Distanz-Fehler (Dijkstra relativ zu Heat Method):")
    print(f"    Mittlerer rel. Fehler:    {np.mean(rel_errors):+.2f}%")
    print(f"    Median rel. Fehler:       {np.median(rel_errors):+.2f}%")
    print(f"    Range:                    {np.min(rel_errors):+.2f}% bis "
          f"{np.max(rel_errors):+.2f}%")
    print(f"\n  σ-Differenz (σ_Dijkstra − σ_Heat):")
    print(f"    Mittelwert:               {np.mean(sigma_diffs):+.3f} mm")
    print(f"    Median:                   {np.median(sigma_diffs):+.3f} mm")
    print(f"    Range:                    {np.min(sigma_diffs):+.3f} bis "
          f"{np.max(sigma_diffs):+.3f} mm")
    print(f"    Max |Δσ|:                 {np.max(np.abs(sigma_diffs)):.3f} mm")

    # Klinische Relevanz
    sc_diffs = [float(r['sigma_diff_mm']) for r in valid
                if r.get('sigma_diff_mm') and r.get('ref_catheters') == 1]
    dc_diffs = [float(r['sigma_diff_mm']) for r in valid
                if r.get('sigma_diff_mm') and r.get('ref_catheters') == 2]
    if sc_diffs:
        print(f"\n  SC-Referenz (n={len(sc_diffs)}): Δσ = {np.mean(sc_diffs):+.3f} mm")
    if dc_diffs:
        print(f"  DC-Referenz (n={len(dc_diffs)}): Δσ = {np.mean(dc_diffs):+.3f} mm")

    print(f"\n  → Die σ-Differenz zwischen Dijkstra und Heat Method ist "
          f"{'vernachlässigbar' if np.max(np.abs(sigma_diffs)) < 0.5 else 'relevant'} "
          f"im Vergleich zu den klinischen SC/DC-Unterschieden (3–5 mm).")


def plot_comparison(summary_rows, all_error_rows):
    """Generate comparison figures."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd

    # Economist palette
    RED = '#E3120B'
    BLUE = '#006BA6'
    TEAL = '#00857C'
    GRAY_DARK = '#333333'
    GRAY_MID = '#76787A'
    GRAY_LIGHT = '#D9D9D9'
    BG_CREAM = '#F7F5F0'
    BG_WHITE = '#FFFFFF'
    ORANGE = '#E67E22'

    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Source Sans 3', 'Source Sans Pro', 'Helvetica Neue'],
        'font.size': 10,
        'axes.facecolor': BG_CREAM, 'axes.edgecolor': GRAY_LIGHT,
        'axes.linewidth': 0.6, 'axes.titlesize': 11, 'axes.titleweight': 'bold',
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.grid': True, 'grid.color': GRAY_LIGHT, 'grid.linewidth': 0.4,
        'xtick.color': GRAY_MID, 'ytick.color': GRAY_MID,
        'legend.frameon': False, 'legend.fontsize': 8,
        'figure.facecolor': BG_WHITE, 'figure.dpi': 150,
        'savefig.facecolor': BG_WHITE, 'savefig.bbox': 'tight',
    })

    df = pd.DataFrame(summary_rows)
    df = df[df['sigma_dijkstra'].apply(lambda x: x != '' and x is not None)].copy()
    df['sigma_dijkstra'] = df['sigma_dijkstra'].astype(float)
    df['sigma_heat'] = df['sigma_heat'].astype(float)
    df['sigma_diff_mm'] = df['sigma_diff_mm'].astype(float)
    df['mean_rel_error_pct'] = df['mean_rel_error_pct'].astype(float)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))

    # Panel A: σ_dijkstra vs σ_heat (identity plot)
    ax = axes[0]
    smax = max(df['sigma_dijkstra'].max(), df['sigma_heat'].max()) * 1.1
    ax.plot([0, smax], [0, smax], '--', color=GRAY_LIGHT, linewidth=1.2, zorder=1)
    sc = df[df['ref_catheters'] == 1]
    dc = df[df['ref_catheters'] == 2]
    ax.scatter(sc['sigma_heat'], sc['sigma_dijkstra'], c=BLUE, s=30, zorder=3,
               label=f'SC (n={len(sc)})', alpha=0.8, edgecolors='white', linewidths=0.5)
    ax.scatter(dc['sigma_heat'], dc['sigma_dijkstra'], c=RED, s=30, zorder=3,
               label=f'DC (n={len(dc)})', alpha=0.8, edgecolors='white', linewidths=0.5)
    ax.set_xlabel('σ Heat Method (mm)')
    ax.set_ylabel('σ Dijkstra (mm)')
    ax.set_title('A  σ: Dijkstra vs. Heat Method', loc='left', fontsize=10)
    ax.legend(loc='upper left', fontsize=7)
    ax.set_aspect('equal')
    ax.plot([0, 1], [1.03, 1.03], transform=ax.transAxes,
            color=RED, linewidth=2.5, clip_on=False, solid_capstyle='butt')

    # Panel B: σ difference vs mean edge length
    ax = axes[1]
    ax.axhline(y=0, color=GRAY_LIGHT, linewidth=1.0)
    ax.scatter(df['mean_edge_mm'], df['sigma_diff_mm'], c=TEAL, s=30, alpha=0.7,
               edgecolors='white', linewidths=0.5)
    ax.set_xlabel('Mean edge length (mm)')
    ax.set_ylabel('Δσ = σ_Dijkstra − σ_Heat (mm)')
    ax.set_title('B  σ-Differenz vs. Mesh-Auflösung', loc='left', fontsize=10)
    ax.plot([0, 1], [1.03, 1.03], transform=ax.transAxes,
            color=RED, linewidth=2.5, clip_on=False, solid_capstyle='butt')

    # Panel C: Relative distance error as function of geodesic distance (aggregated)
    ax = axes[2]
    if all_error_rows:
        edf = pd.DataFrame(all_error_rows)
        agg = edf.groupby('dist_center_mm').agg(
            mean_err=('mean_rel_error', 'mean'),
            std_err=('mean_rel_error', 'std'),
        ).reset_index()
        ax.fill_between(agg['dist_center_mm'],
                         (agg['mean_err'] - agg['std_err']) * 100,
                         (agg['mean_err'] + agg['std_err']) * 100,
                         alpha=0.15, color=BLUE)
        ax.plot(agg['dist_center_mm'], agg['mean_err'] * 100,
                '-o', color=BLUE, markersize=4, linewidth=1.3)
    ax.axhline(y=0, color=GRAY_LIGHT, linewidth=1.0)
    ax.set_xlabel('Geodesic distance (mm)')
    ax.set_ylabel('Relative error (%)')
    ax.set_title('C  Dijkstra-Fehler vs. Distanz', loc='left', fontsize=10)
    ax.plot([0, 1], [1.03, 1.03], transform=ax.transAxes,
            color=RED, linewidth=2.5, clip_on=False, solid_capstyle='butt')

    fig.tight_layout()

    for outpath in [
        os.path.join(OUTPUT_DIR, 'geodesic_comparison.pdf'),
        os.path.join(OUTPUT_DIR, 'geodesic_comparison.png'),
    ]:
        fig.savefig(outpath, dpi=150)
        print(f"Figure: {outpath}")

    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Geodäsik-Vergleich: Dijkstra vs. Heat Method')
    parser.add_argument('--plot', action='store_true',
                        help='Abbildungen erzeugen')
    parser.add_argument('--export-meshes', action='store_true',
                        help='Meshes als .npz exportieren')
    args = parser.parse_args()

    print("=" * 60)
    print("Geodäsik-Vergleich: Dijkstra vs. Heat Method")
    print("=" * 60)

    summary_rows, all_error_rows = run_comparison(export_meshes=args.export_meshes)

    # Filter valid results
    valid = [r for r in summary_rows if 'sigma_dijkstra' in r and r.get('sigma_dijkstra')]
    n_failed = len(summary_rows) - len(valid)
    if n_failed:
        print(f"\n⚠ {n_failed} maps failed (see 'error' column in CSV)")

    print_summary(summary_rows)

    if args.plot:
        plot_comparison(summary_rows, all_error_rows)

    print("\nDone.")
