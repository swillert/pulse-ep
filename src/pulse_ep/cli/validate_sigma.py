#!/usr/bin/env python3
"""
ARBEITSPAKET 1 — Validierung der σ-Metrik mittels synthetischer Felder

Erzeugt auf realen atrialen Meshes synthetische Score-Felder mit bekanntem σ₀,
führt die bestehende Analysepipeline (Ursprungsbestimmung, Radialprofil, Gauß-Fit)
durch und vergleicht geschätztes σ̂ mit vorgegebenem σ₀.

Geodätische Distanzen werden mittels der Heat Method (Crane et al. 2017)
berechnet, die die exakte Oberflächendistanz auf der Dreiecksmannigfaltigkeit
bestimmt. Optional kann mit --dijkstra auf die alte Dijkstra-Approximation
umgeschaltet werden (für Vergleichszwecke).

Ergebnisse:
  - decay_profiles/validation_summary.csv     Zeile pro (Mesh × σ₀ × Noise × Trial)
  - decay_profiles/validation_bias.csv        Aggregierte Bias-Statistik
  - _figures/-kompatible Abbildung (optional via --plot)

Nutzung:
  python3 validate_sigma.py              # Vollständiger Lauf (Heat Method)
  python3 validate_sigma.py --plot       # + Abbildung erzeugen
  python3 validate_sigma.py --dijkstra   # Dijkstra statt Heat Method
  python3 validate_sigma.py --no-db      # Offline-Modus mit gespeicherten CSVs
"""

import os
import csv
import argparse
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import shortest_path
from scipy.optimize import curve_fit
import potpourri3d as pp3d

# ── Pipeline-Bausteine aus spatial_decay.py ──────────────────
from spatial_decay import build_adjacency_matrix, compute_geodesic_distances


# ── Geodäsik-Methode (wird in main() gesetzt) ───────────────
USE_HEAT_METHOD = True   # Default: Heat Method; --dijkstra schaltet auf False


def compute_heat_distances(vertices, triangles, origin_idx):
    """Geodätische Distanzen via Heat Method (Crane et al. 2017)."""
    verts = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(triangles, dtype=np.int64)
    solver = pp3d.MeshHeatMethodDistanceSolver(verts, faces)
    return solver.compute_distance(origin_idx)


# ═════════════════════════════════════════════════════════════
#  KONFIGURATION
# ═════════════════════════════════════════════════════════════

# Alle 56 klinischen Meshes (nach Fragmentierungsfilter)
SELECTED_MAPS = [
    (mid, '') for mid in [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 35, 51, 52, 53, 54,
        62, 63, 64, 65, 75, 76, 77, 78, 86, 88, 89, 104, 117, 139, 140, 141, 144, 145,
    ]
]

# Vorgegebene σ₀-Werte in mm
SIGMA_TRUE = [3, 5, 8, 10, 15, 20, 25, 30]

# Rauschstufen (relative Standardabweichung des Gaußrauschens)
NOISE_LEVELS = [0.0, 0.05, 0.10, 0.15]

# Missing-Value-Anteil
MISSING_FRACTION = 0.05

# Anzahl Wiederholungen pro Kombination (für Bootstrap-Varianz)
N_TRIALS = 20

# Gauß-Fit-Parameter (konsistent mit generate_figures.py)
BIN_WIDTH = 2       # mm
SIGMA_UPPER = 200   # mm — generous upper bound for σ (matching clinical pipeline)
SIGMA_BOUNDS = (0.1, 200.0)

# Baseline-Score (realistisch für Pace-Mapping)
BASELINE_SCORE = 65.0   # % — typischer Baseline bei großer Distanz
AMPLITUDE = 35.0         # Prozentpunkte über Baseline

OUTPUT_DIR = './decay_profiles'


# ═════════════════════════════════════════════════════════════
#  HILFSFUNKTIONEN
# ═════════════════════════════════════════════════════════════

def gauss(d, A, sigma, B):
    """Gauß-Funktion (identisch mit generate_figures.py)."""
    return A * np.exp(-d**2 / (2 * sigma**2)) + B


def generate_synthetic_field(geo_dist, sigma0, noise_level, missing_frac, rng,
                             amplitude=AMPLITUDE, baseline=BASELINE_SCORE):
    """Erzeuge synthetisches Score-Feld auf Basis geodätischer Distanzen.

    S(v) = A · exp(-d² / 2σ₀²) + B + ε

    Parameters
    ----------
    geo_dist : ndarray
        Geodätische Distanzen vom Ursprung (kann inf enthalten).
    sigma0 : float
        Wahre Standardabweichung in mm.
    noise_level : float
        Relative Rauschstärke (0.0 = kein Rauschen).
    missing_frac : float
        Anteil zufällig maskierter Vertices.
    rng : np.random.Generator
        Zufallsgenerator für Reproduzierbarkeit.
    amplitude : float
        Amplitude über Baseline in Prozentpunkten.
    baseline : float
        Baseline-Score bei großer Distanz.

    Returns
    -------
    scores : ndarray
        Synthetische Matching-Scores (NaN für unreachable / missing).
    """
    n = len(geo_dist)
    scores = np.full(n, np.nan)

    reachable = np.isfinite(geo_dist)
    d = geo_dist[reachable]

    # Deterministisches Feld
    s = amplitude * np.exp(-d**2 / (2 * sigma0**2)) + baseline

    # Gaußrauschen
    if noise_level > 0:
        noise_std = noise_level * amplitude  # absolut, bezogen auf Amplitude
        s += rng.normal(0, noise_std, size=len(s))

    # Clipping auf [50, 100] (realistischer Score-Bereich)
    s = np.clip(s, 50.0, 100.0)

    scores[reachable] = s

    # Missing values
    if missing_frac > 0:
        reachable_idx = np.where(reachable)[0]
        n_missing = int(missing_frac * len(reachable_idx))
        if n_missing > 0:
            missing_idx = rng.choice(reachable_idx, size=n_missing, replace=False)
            scores[missing_idx] = np.nan

    return scores


def fit_synthetic_profile(geo_dist, scores, bin_width=BIN_WIDTH):
    """Bin-Aggregation + Gauß-Fit auf synthetisches Feld.

    Matches the clinical pipeline (verify_thesis_values.py):
    - Binning uses full mesh distance range (not a fixed window)
    - σ upper bound = SIGMA_BOUNDS[1] (200 mm)

    Returns
    -------
    dict mit sigma_hat, A_hat, B_hat, r_squared, n_bins
    oder None bei Fit-Fehler.
    """
    # Nur endliche Distanzen und nicht-NaN-Scores
    valid = np.isfinite(geo_dist) & ~np.isnan(scores)
    d_valid = geo_dist[valid]
    s_valid = scores[valid]

    if len(d_valid) < 10:
        return None

    # Binning — use full mesh distance (matching clinical pipeline)
    max_dist = d_valid.max() if len(d_valid) > 0 else 0
    bins = np.arange(0, max_dist + bin_width, bin_width)
    bin_idx = np.digitize(d_valid, bins) - 1  # 0-basiert
    n_bins_total = len(bins) - 1

    bin_means = np.full(n_bins_total, np.nan)
    for k in range(n_bins_total):
        mask = bin_idx == k
        if np.sum(mask) >= 3:  # Mindestens 3 Vertices pro Bin
            bin_means[k] = np.mean(s_valid[mask])

    valid_bins = ~np.isnan(bin_means)
    if np.sum(valid_bins) < 4:
        return None

    d_centers = (np.arange(n_bins_total) + 0.5) * bin_width
    d_fit = d_centers[valid_bins]
    s_fit = bin_means[valid_bins]

    # Gauß-Fit
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

        # R²
        ss_res = np.sum((s_fit - gauss(d_fit, *popt))**2)
        ss_tot = np.sum((s_fit - np.mean(s_fit))**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        return {
            'sigma_hat': abs(sigma_hat),
            'A_hat': A_hat,
            'B_hat': B_hat,
            'r_squared': r_squared,
            'n_bins': int(np.sum(valid_bins)),
        }
    except (RuntimeError, ValueError):
        return None


def load_mesh_from_db(map_id):
    """Lade Mesh aus der Datenbank. Returns (vertices, triangles) als numpy arrays."""
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import EPMapModel

    with get_db_session() as session:
        epmap = session.query(EPMapModel).filter_by(id=map_id).first()
        if epmap is None:
            raise ValueError(f"Map {map_id} nicht gefunden")

        vertices = np.array(epmap.vertices).reshape(-1, 3)
        triangles = np.array(epmap.triangles).reshape(-1, 3)

    return vertices, triangles


def load_mesh_from_csv(map_id, data_dir=OUTPUT_DIR):
    """Lade Mesh-Positionen aus bestehendem decay_map CSV (Offline-Fallback)."""
    fp = os.path.join(data_dir, f'decay_map_{map_id:03d}.csv')
    if not os.path.exists(fp):
        raise FileNotFoundError(f"{fp} nicht gefunden")

    import pandas as pd
    df = pd.read_csv(fp)
    vertices = df[['x', 'y', 'z']].values
    # Kein Zugriff auf Dreiecke im CSV → brauchen wir die DB
    raise NotImplementedError(
        "Für die synthetische Validierung werden die Dreiecksindizes benötigt. "
        "Bitte Datenbank starten (docker-compose up -d db)."
    )


# ═════════════════════════════════════════════════════════════
#  HAUPTLAUF
# ═════════════════════════════════════════════════════════════

def run_validation(use_db=True, seed=42):
    """Führe die vollständige Validierung durch.

    Für jedes Mesh × σ₀ × Noise-Level × Trial:
      1. Lade Mesh und berechne geodätische Distanzen vom Zentroid-Vertex
      2. Erzeuge synthetisches Feld
      3. Bestimme Ursprung (argmax des synthetischen Scores)
      4. Berechne geodätische Distanzen vom gefundenen Ursprung
      5. Führe Gauß-Fit durch
      6. Speichere σ̂ und Bias

    Returns
    -------
    results : list of dict
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rng = np.random.default_rng(seed)

    geo_method = 'heat' if USE_HEAT_METHOD else 'dijkstra'
    print(f"  Geodäsik-Methode: {geo_method}")

    results = []

    for map_id, description in SELECTED_MAPS:
        print(f"\n{'='*60}")
        print(f"Mesh {map_id}: {description}")
        print(f"{'='*60}")

        # Mesh laden
        if use_db:
            vertices, triangles = load_mesh_from_db(map_id)
        else:
            load_mesh_from_csv(map_id)  # Wirft NotImplementedError

        n_verts = len(vertices)
        print(f"  Vertices: {n_verts}, Dreiecke: {len(triangles)}")

        # Einen gut verbundenen Vertex als wahren Ursprung wählen
        # → Vertex nahe dem geometrischen Schwerpunkt der Hauptkomponente
        adj = build_adjacency_matrix(vertices, triangles)

        # Schwerpunkt berechnen
        centroid = vertices.mean(axis=0)
        dists_to_centroid = np.linalg.norm(vertices - centroid, axis=1)
        # Sortiere nach Nähe zum Schwerpunkt, nehme den nächsten
        true_origin = int(np.argmin(dists_to_centroid))

        print(f"  Wahrer Ursprung: Vertex {true_origin} "
              f"(Pos: {vertices[true_origin]})")

        # Geodätische Distanzen vom wahren Ursprung
        if USE_HEAT_METHOD:
            geo_dist_true = compute_heat_distances(vertices, triangles, true_origin)
        else:
            geo_dist_true = compute_geodesic_distances(adj, true_origin)
        n_reachable = np.sum(np.isfinite(geo_dist_true))
        max_geo = np.nanmax(geo_dist_true[np.isfinite(geo_dist_true)])
        print(f"  Erreichbar: {n_reachable}/{n_verts}, max geo dist: {max_geo:.1f} mm")

        if n_reachable < 100:
            print(f"  ⚠ Zu wenige erreichbare Vertices — überspringe")
            continue

        # Mittlere Kantenlänge für Dokumentation
        edge_lengths = []
        for tri in triangles:
            for i in range(3):
                v0, v1 = tri[i], tri[(i + 1) % 3]
                edge_lengths.append(np.linalg.norm(vertices[v0] - vertices[v1]))
        mean_edge = np.mean(edge_lengths)
        print(f"  Mittlere Kantenlänge: {mean_edge:.2f} mm")

        for sigma0 in SIGMA_TRUE:
            for noise_level in NOISE_LEVELS:
                for trial in range(N_TRIALS):

                    # 1. Synthetisches Feld erzeugen (auf Basis wahrer Distanzen)
                    scores = generate_synthetic_field(
                        geo_dist_true, sigma0, noise_level, MISSING_FRACTION, rng
                    )

                    # 2. Ursprung bestimmen (wie in spatial_decay.py)
                    score_clean = np.where(np.isnan(scores), 0.0, scores)
                    found_origin = int(np.argmax(score_clean))

                    # Abstand zwischen wahrem und gefundenem Ursprung
                    origin_offset = geo_dist_true[found_origin] if np.isfinite(
                        geo_dist_true[found_origin]) else np.nan

                    # 3. Geodätische Distanzen vom gefundenen Ursprung
                    if found_origin == true_origin:
                        geo_dist_found = geo_dist_true
                    elif USE_HEAT_METHOD:
                        geo_dist_found = compute_heat_distances(vertices, triangles, found_origin)
                    else:
                        geo_dist_found = compute_geodesic_distances(adj, found_origin)

                    # 4. Gauß-Fit
                    fit_result = fit_synthetic_profile(geo_dist_found, scores)

                    if fit_result is not None:
                        sigma_hat = fit_result['sigma_hat']
                        bias = sigma_hat - sigma0
                        rel_bias = bias / sigma0 * 100
                    else:
                        sigma_hat = np.nan
                        bias = np.nan
                        rel_bias = np.nan

                    results.append({
                        'map_id': map_id,
                        'n_vertices': n_verts,
                        'mean_edge_mm': round(mean_edge, 2),
                        'sigma_true': sigma0,
                        'noise_level': noise_level,
                        'missing_frac': MISSING_FRACTION,
                        'trial': trial,
                        'true_origin': true_origin,
                        'found_origin': found_origin,
                        'origin_offset_mm': round(origin_offset, 3) if np.isfinite(origin_offset) else '',
                        'sigma_hat': round(sigma_hat, 3) if np.isfinite(sigma_hat) else '',
                        'bias_mm': round(bias, 3) if np.isfinite(bias) else '',
                        'rel_bias_pct': round(rel_bias, 2) if np.isfinite(rel_bias) else '',
                        'A_hat': round(fit_result['A_hat'], 2) if fit_result else '',
                        'B_hat': round(fit_result['B_hat'], 2) if fit_result else '',
                        'r_squared': round(fit_result['r_squared'], 4) if fit_result else '',
                        'n_bins': fit_result['n_bins'] if fit_result else '',
                    })

                # Kurzstatus (nur beim letzten Trial)
                last = results[-1]
                if last['sigma_hat'] != '':
                    print(f"  σ₀={sigma0:>2d} mm, noise={noise_level:.0%}: "
                          f"σ̂={last['sigma_hat']:.1f} mm, "
                          f"bias={last['bias_mm']:+.2f} mm, "
                          f"R²={last['r_squared']:.3f}, "
                          f"origin_offset={last['origin_offset_mm']} mm")
                else:
                    print(f"  σ₀={sigma0:>2d} mm, noise={noise_level:.0%}: FIT FAILED")

    return results


def compute_aggregated_bias(results):
    """Berechne aggregierten Bias mit Bootstrap-Konfidenzintervallen."""
    import pandas as pd

    df = pd.DataFrame(results)
    df = df[df['sigma_hat'] != ''].copy()
    df['sigma_hat'] = df['sigma_hat'].astype(float)
    df['bias_mm'] = df['bias_mm'].astype(float)
    df['rel_bias_pct'] = df['rel_bias_pct'].astype(float)
    df['r_squared'] = df['r_squared'].astype(float)

    agg_rows = []

    for (sigma0, noise), grp in df.groupby(['sigma_true', 'noise_level']):
        n = len(grp)
        sigma_hats = grp['sigma_hat'].values
        biases = grp['bias_mm'].values

        mean_sigma = np.mean(sigma_hats)
        std_sigma = np.std(sigma_hats, ddof=1) if n > 1 else 0
        mean_bias = np.mean(biases)
        median_bias = np.median(biases)

        # Bootstrap 95 % CI für den Bias
        rng = np.random.default_rng(123)
        n_boot = 2000
        boot_means = np.array([
            np.mean(rng.choice(biases, size=n, replace=True))
            for _ in range(n_boot)
        ])
        ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])

        mean_r2 = np.mean(grp['r_squared'].values)
        n_failed = len(results) // max(1, len(df)) * n  # Approximation

        agg_rows.append({
            'sigma_true': sigma0,
            'noise_level': noise,
            'n_fits': n,
            'mean_sigma_hat': round(mean_sigma, 3),
            'std_sigma_hat': round(std_sigma, 3),
            'mean_bias_mm': round(mean_bias, 3),
            'median_bias_mm': round(median_bias, 3),
            'ci95_lo': round(ci_lo, 3),
            'ci95_hi': round(ci_hi, 3),
            'mean_r_squared': round(mean_r2, 4),
        })

    return agg_rows


def save_results(results, agg_rows):
    """Speichere Ergebnisse als CSV."""
    # Detaillierte Ergebnisse
    summary_path = os.path.join(OUTPUT_DIR, 'validation_summary.csv')
    fieldnames = [
        'map_id', 'n_vertices', 'mean_edge_mm',
        'sigma_true', 'noise_level', 'missing_frac', 'trial',
        'true_origin', 'found_origin', 'origin_offset_mm',
        'sigma_hat', 'bias_mm', 'rel_bias_pct',
        'A_hat', 'B_hat', 'r_squared', 'n_bins',
    ]
    with open(summary_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nDetaillierte Ergebnisse: {summary_path}")

    # Aggregierte Bias-Statistik
    bias_path = os.path.join(OUTPUT_DIR, 'validation_bias.csv')
    with open(bias_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(agg_rows[0].keys()))
        writer.writeheader()
        writer.writerows(agg_rows)
    print(f"Bias-Statistik: {bias_path}")


def print_summary(agg_rows):
    """Drucke zusammenfassende Tabelle."""
    print(f"\n{'='*75}")
    print("ZUSAMMENFASSUNG: Bias der σ-Schätzung")
    print(f"{'='*75}")
    print(f"{'σ₀ (mm)':>8} {'Noise':>6} {'n':>4} {'σ̂ mean':>8} {'σ̂ std':>7} "
          f"{'Bias':>7} {'95% CI':>16} {'R²':>6}")
    print(f"{'-'*75}")

    for row in agg_rows:
        ci_str = f"[{row['ci95_lo']:+.2f}, {row['ci95_hi']:+.2f}]"
        print(f"{row['sigma_true']:>8.0f} {row['noise_level']:>6.0%} "
              f"{row['n_fits']:>4d} {row['mean_sigma_hat']:>8.2f} "
              f"{row['std_sigma_hat']:>7.3f} {row['mean_bias_mm']:>+7.3f} "
              f"{ci_str:>16} {row['mean_r_squared']:>6.3f}")


# ═════════════════════════════════════════════════════════════
#  ABBILDUNG: σ₀ vs σ̂
# ═════════════════════════════════════════════════════════════

def plot_validation(agg_rows):
    """Erzeuge Abbildung σ₀ vs σ̂ (Economist-Stil, kompatibel mit thesis-figures)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # Economist-Palette (konsistent mit generate_figures.py)
    RED = '#E3120B'
    BLUE = '#006BA6'
    TEAL = '#00857C'
    GRAY_DARK = '#333333'
    GRAY_MID = '#76787A'
    GRAY_LIGHT = '#D9D9D9'
    BG_CREAM = '#F7F5F0'
    BG_WHITE = '#FFFFFF'
    ORANGE = '#E67E22'

    NOISE_COLORS = {0.0: BLUE, 0.05: TEAL, 0.10: ORANGE, 0.15: RED}
    NOISE_LABELS = {0.0: 'Kein Rauschen', 0.05: '5 %', 0.10: '10 %', 0.15: '15 %'}

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

    import pandas as pd
    df = pd.DataFrame(agg_rows)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.8))

    # ── Panel A: σ₀ vs σ̂ ──
    ax1.plot([0, 35], [0, 35], '--', color=GRAY_LIGHT, linewidth=1.2,
             zorder=1, label='Ideallinie')

    for noise in sorted(df['noise_level'].unique()):
        sub = df[df['noise_level'] == noise].sort_values('sigma_true')
        color = NOISE_COLORS.get(noise, GRAY_MID)
        label = NOISE_LABELS.get(noise, f'{noise:.0%}')

        yerr_lo = (sub['mean_sigma_hat'] - sub['ci95_lo']).clip(lower=0)
        yerr_hi = (sub['ci95_hi'] - sub['mean_sigma_hat']).clip(lower=0)
        ax1.errorbar(
            sub['sigma_true'], sub['mean_sigma_hat'],
            yerr=[yerr_lo, yerr_hi],
            fmt='o-', color=color, markersize=5, linewidth=1.3,
            capsize=3, capthick=0.8, elinewidth=0.8,
            label=label, zorder=3
        )

    ax1.set_xlabel('Vorgegebenes σ₀ (mm)')
    ax1.set_ylabel('Geschätztes σ̂ (mm)')
    ax1.set_title('A  Genauigkeit der σ-Schätzung', loc='left', fontsize=10)
    ax1.legend(title='Rauschen', loc='upper left', fontsize=7, title_fontsize=7)
    ax1.set_xlim(0, 33)
    ax1.set_ylim(0, 33)
    ax1.set_aspect('equal')

    # Topline
    ax1.plot([0, 1], [1.03, 1.03], transform=ax1.transAxes,
             color=RED, linewidth=2.5, clip_on=False, solid_capstyle='butt')

    # ── Panel B: Bias vs σ₀ ──
    ax2.axhline(y=0, color=GRAY_LIGHT, linewidth=1.0)

    for noise in sorted(df['noise_level'].unique()):
        sub = df[df['noise_level'] == noise].sort_values('sigma_true')
        color = NOISE_COLORS.get(noise, GRAY_MID)
        label = NOISE_LABELS.get(noise, f'{noise:.0%}')

        ax2.fill_between(
            sub['sigma_true'], sub['ci95_lo'], sub['ci95_hi'],
            alpha=0.12, color=color, linewidth=0
        )
        ax2.plot(sub['sigma_true'], sub['mean_bias_mm'],
                 'o-', color=color, markersize=5, linewidth=1.3,
                 label=label, zorder=3)

    ax2.set_xlabel('Vorgegebenes σ₀ (mm)')
    ax2.set_ylabel('Bias σ̂ − σ₀ (mm)')
    ax2.set_title('B  Systematische Abweichung', loc='left', fontsize=10)
    ax2.legend(title='Rauschen', loc='upper left', fontsize=7, title_fontsize=7)

    ax2.plot([0, 1], [1.03, 1.03], transform=ax2.transAxes,
             color=RED, linewidth=2.5, clip_on=False, solid_capstyle='butt')

    fig.tight_layout()

    # Speichern: immer nach OUTPUT_DIR, optional zusätzlich in PULSE_THESIS_FIGURES
    outdirs = [OUTPUT_DIR]
    thesis_dir = os.environ.get('PULSE_THESIS_FIGURES')
    if thesis_dir and os.path.isdir(thesis_dir):
        outdirs.append(thesis_dir)
    for outdir in outdirs:
        outpath = os.path.join(outdir, 'validation_sigma.pdf')
        fig.savefig(outpath, dpi=150)
        print(f"Abbildung: {outpath}")

    plt.close(fig)


# ═════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AP1: Validierung der σ-Metrik mittels synthetischer Felder')
    parser.add_argument('--plot', action='store_true',
                        help='Abbildung erzeugen')
    parser.add_argument('--no-db', action='store_true',
                        help='Offline-Modus (ohne Datenbank)')
    parser.add_argument('--dijkstra', action='store_true',
                        help='Dijkstra statt Heat Method verwenden (für Vergleich)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed für Reproduzierbarkeit')
    parser.add_argument('--trials', type=int, default=None,
                        help='Anzahl Trials pro Kombination (überschreibt N_TRIALS)')
    args = parser.parse_args()

    if args.trials is not None:
        N_TRIALS = args.trials

    if args.dijkstra:
        USE_HEAT_METHOD = False

    geo_label = 'Dijkstra' if args.dijkstra else 'Heat Method (Crane et al. 2017)'
    print("="*60)
    print("AP1: Validierung der σ-Metrik mittels synthetischer Felder")
    print(f"     Geodäsik: {geo_label}")
    print("="*60)
    print(f"  Meshes:       {len(SELECTED_MAPS)}")
    print(f"  σ₀-Werte:     {SIGMA_TRUE}")
    print(f"  Rauschstufen: {NOISE_LEVELS}")
    print(f"  Missing:      {MISSING_FRACTION:.0%}")
    print(f"  Trials:       {N_TRIALS}")
    print(f"  Gesamtkombinationen: "
          f"{len(SELECTED_MAPS) * len(SIGMA_TRUE) * len(NOISE_LEVELS) * N_TRIALS}")

    results = run_validation(use_db=not args.no_db, seed=args.seed)

    # Aggregation
    valid_results = [r for r in results if r['sigma_hat'] != '']
    n_failed = len(results) - len(valid_results)
    print(f"\n  Erfolgreiche Fits: {len(valid_results)}/{len(results)}")
    if n_failed > 0:
        print(f"  Fehlgeschlagene Fits: {n_failed}")

    agg_rows = compute_aggregated_bias(results)
    save_results(results, agg_rows)
    print_summary(agg_rows)

    if args.plot:
        plot_validation(agg_rows)

    print("\nDone.")
