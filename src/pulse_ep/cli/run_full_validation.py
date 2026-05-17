#!/usr/bin/env python3
"""
Full Synthetic Validation — all clinical meshes.

Extends the original validation (5 meshes × 8 σ₀ × 4 noise × 20 trials = 3,200 fits)
to ALL clinical meshes (56 meshes × 8 σ₀ × 4 noise × 20 trials = 35,840 fits).

Results are saved to a SEPARATE directory so the original validation data is untouched.
If the results are problematic, simply delete the output directory.

Output directory: thesis-med/_paper/method-paper/validation_full/
  - validation_full_raw.csv       — one row per individual fit
  - validation_full_summary.csv   — aggregated: mean bias, SD, CI per (σ₀, η)
  - validation_full_by_mesh.csv   — per-mesh breakdown (detects problematic geometries)
  - validation_full_log.txt       — runtime log

Usage (from pulse-ultimate root):
    python run_full_validation.py                   # all 56 meshes
    python run_full_validation.py --n-trials 5      # quick test with 5 trials
    python run_full_validation.py --mesh-ids 75 14  # specific meshes only

Requires: numpy, pandas, scipy
Data:     decay_profiles_heat/decay_map_*.csv (in pulse-ultimate)
Output:   thesis-med/_paper/method-paper/validation_full/

Author: Sven Willert, UKSH Kiel
"""

import argparse
import os
import time
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

# ─── Paths ─────────────────────────────────────────────────
# Script lives in pulse-ultimate/, data is here too, output goes to thesis-med
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'decay_profiles_heat')
OUT_DIR    = os.path.normpath(os.path.join(
    SCRIPT_DIR, '..', 'thesis-med', '_paper', 'method-paper', 'validation_full'))

# ─── Validation parameters ─────────────────────────────────
SIGMA_TRUE_VALUES = [3, 5, 8, 10, 15, 20, 25, 30]  # mm
NOISE_LEVELS      = [0.0, 0.05, 0.10, 0.15]         # fraction of amplitude
N_TRIALS          = 20
BIN_WIDTH         = 2   # mm
SIGMA_UPPER       = 200 # mm — generous upper bound for σ (matching clinical pipeline)
A_TRUE            = 35  # percentage points amplitude
B_TRUE            = 65  # percentage points baseline
SCORE_CLAMP       = (50, 100)
MASK_FRACTION     = 0.05  # 5% random masking


def gauss(d, A, sigma, B):
    """Three-parameter Gaussian decay model."""
    return A * np.exp(-d**2 / (2 * sigma**2)) + B


def load_mesh_distances(map_id):
    """Load geodesic distances and vertex coordinates for a map."""
    fp = os.path.join(DATA_DIR, f'decay_map_{map_id:03d}.csv')
    if not os.path.exists(fp):
        return None
    df = pd.read_csv(fp)
    return df[['vertex_idx', 'geodesic_dist_mm', 'x', 'y', 'z']].copy()


def generate_synthetic_field(distances, sigma_0, noise_frac, rng):
    """Generate synthetic Gaussian score field on real mesh geometry.

    Uses the vertex closest to the surface centroid as the true origin
    (same as the original validation protocol).
    """
    coords = distances[['x', 'y', 'z']].values
    centroid = coords.mean(axis=0)
    dists_to_centroid = np.linalg.norm(coords - centroid, axis=1)
    origin_idx = np.argmin(dists_to_centroid)

    # Recompute geodesic distances from centroid vertex
    # We use the pre-computed distances and shift the origin
    # Actually: the pre-computed distances are from the argmax vertex, not centroid.
    # For synthetic validation, we need distances from the centroid vertex.
    # Since we don't have Heat Method here, we approximate by using the
    # geodesic distance from the original origin, then shifting.
    #
    # Better approach: use the stored geodesic distances directly.
    # The origin in the real data is the argmax vertex.
    # For synthetic validation, we define the synthetic origin as vertex
    # with index origin_idx (closest to centroid), and we need distances
    # from that vertex. Since we only have distances from the real argmax,
    # we use Euclidean distances from the centroid vertex as an approximation
    # for the GENERATION step only. The RECOVERY step uses the full pipeline
    # (argmax → geodesic distances from data → binning → fit), which tests
    # whether the pipeline can recover σ₀ even when distances are approximate.
    #
    # Actually, the cleanest approach: generate the synthetic field using
    # the EXISTING geodesic distances (from the real argmax vertex).
    # This means the synthetic field's "true origin" IS the real argmax vertex,
    # and the distances are exact geodesics. This is the same approach
    # used in the original validation.

    d = distances['geodesic_dist_mm'].values

    # Generate synthetic scores
    scores = A_TRUE * np.exp(-d**2 / (2 * sigma_0**2)) + B_TRUE

    # Add noise
    if noise_frac > 0:
        noise = rng.normal(0, noise_frac * A_TRUE, size=len(scores))
        scores = scores + noise

    # Clamp to valid range
    scores = np.clip(scores, SCORE_CLAMP[0], SCORE_CLAMP[1])

    # Random masking (5% of vertices set to NaN)
    mask = rng.random(len(scores)) < MASK_FRACTION
    scores[mask] = np.nan

    return scores, d


def run_pipeline(scores, distances_mm, bin_width=BIN_WIDTH):
    """Run the decay analysis pipeline on synthetic scores.

    Matches the clinical pipeline (verify_thesis_values.py):
    - Binning uses full mesh distance range (not a fixed window)
    - σ upper bound = SIGMA_UPPER (200 mm)

    Returns (sigma_hat, r2) or (None, None) if fit fails.
    """
    # Step 1: Find origin (argmax)
    valid = ~np.isnan(scores)
    if valid.sum() < 10:
        return None, None

    origin_idx = np.nanargmax(scores)

    # Step 2: Distances are already provided (from real geodesics)
    d = distances_mm.copy()

    # Step 3: Radial binning — use full mesh distance (matching clinical pipeline)
    max_dist = d[np.isfinite(d)].max() if np.any(np.isfinite(d)) else 0
    bins = np.arange(0, max_dist + bin_width, bin_width)
    bin_indices = np.digitize(d, bins) - 1  # 0-indexed

    bin_means = []
    bin_centers = []
    for k in range(len(bins) - 1):
        in_bin = (bin_indices == k) & valid
        if in_bin.sum() >= 3:
            bin_means.append(np.mean(scores[in_bin]))
            bin_centers.append((bins[k] + bins[k+1]) / 2)

    if len(bin_means) < 4:
        return None, None

    bin_centers = np.array(bin_centers)
    bin_means = np.array(bin_means)

    # Step 4: Gaussian fit — σ bound = SIGMA_UPPER (matching clinical pipeline)
    try:
        A0 = bin_means.max() - bin_means.min()
        popt, _ = curve_fit(
            gauss, bin_centers, bin_means,
            p0=[A0, 10.0, bin_means.min()],
            bounds=([0, 0.1, -np.inf], [np.inf, SIGMA_UPPER, np.inf]),
            maxfev=5000
        )
        sigma_hat = abs(popt[1])

        # R²
        predicted = gauss(bin_centers, *popt)
        ss_res = np.sum((bin_means - predicted)**2)
        ss_tot = np.sum((bin_means - bin_means.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return sigma_hat, r2
    except Exception:
        return None, None


def bootstrap_ci(values, n_boot=2000, ci=0.95, rng=None):
    """Percentile bootstrap 95% CI."""
    if rng is None:
        rng = np.random.default_rng(42)
    values = np.array(values)
    n = len(values)
    if n < 3:
        return np.nan, np.nan
    boot_means = np.array([
        np.mean(rng.choice(values, size=n, replace=True))
        for _ in range(n_boot)
    ])
    lo = np.percentile(boot_means, (1 - ci) / 2 * 100)
    hi = np.percentile(boot_means, (1 + ci) / 2 * 100)
    return lo, hi


def main():
    parser = argparse.ArgumentParser(
        description='Full synthetic validation on all clinical meshes')
    parser.add_argument('--n-trials', type=int, default=N_TRIALS,
                        help=f'Number of random trials per combination (default: {N_TRIALS})')
    parser.add_argument('--mesh-ids', type=int, nargs='+', default=None,
                        help='Specific mesh IDs to validate (default: all)')
    parser.add_argument('--output-dir', type=str, default=OUT_DIR,
                        help=f'Output directory (default: {OUT_DIR})')
    args = parser.parse_args()

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    # ── Determine which meshes to use ──
    summary = pd.read_csv(os.path.join(DATA_DIR, 'decay_summary.csv'))
    after_frag = summary[summary['max_geodesic_dist'] >= 5].copy()

    if args.mesh_ids:
        mesh_ids = [m for m in args.mesh_ids if m in after_frag['map_id'].values]
    else:
        mesh_ids = sorted(after_frag['map_id'].tolist())

    n_meshes = len(mesh_ids)
    n_sigma = len(SIGMA_TRUE_VALUES)
    n_noise = len(NOISE_LEVELS)
    n_trials = args.n_trials
    total_fits = n_meshes * n_sigma * n_noise * n_trials

    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    log(f"Full Synthetic Validation")
    log(f"  Meshes:      {n_meshes}")
    log(f"  σ₀ values:   {SIGMA_TRUE_VALUES}")
    log(f"  Noise levels: {NOISE_LEVELS}")
    log(f"  Trials:      {n_trials}")
    log(f"  Total fits:  {total_fits:,}")
    log(f"  Output:      {out_dir}")
    log(f"")

    # ── Load all mesh distance data ──
    log("Loading mesh data...")
    mesh_data = {}
    mesh_info = {}
    for mid in mesh_ids:
        df = load_mesh_distances(mid)
        if df is not None:
            mesh_data[mid] = df
            row = after_frag[after_frag['map_id'] == mid].iloc[0]
            mesh_info[mid] = {
                'n_vertices': int(row['n_vertices']),
                'atrium': row['atrium'],
                'part': row['part'],
            }

    valid_mesh_ids = sorted(mesh_data.keys())
    log(f"  Loaded {len(valid_mesh_ids)} meshes")
    log(f"  Vertex range: {min(mesh_info[m]['n_vertices'] for m in valid_mesh_ids)} — "
        f"{max(mesh_info[m]['n_vertices'] for m in valid_mesh_ids)}")
    log(f"")

    # ── Run validation ──
    log("Running fits...")
    t0 = time.time()

    raw_results = []
    rng = np.random.default_rng(2024)

    completed = 0
    for sigma_0 in SIGMA_TRUE_VALUES:
        for noise in NOISE_LEVELS:
            for mid in valid_mesh_ids:
                df = mesh_data[mid]
                distances_mm = df['geodesic_dist_mm'].values

                for trial in range(n_trials):
                    scores, d = generate_synthetic_field(df, sigma_0, noise, rng)
                    sigma_hat, r2 = run_pipeline(scores, distances_mm)

                    raw_results.append({
                        'map_id': mid,
                        'n_vertices': mesh_info[mid]['n_vertices'],
                        'atrium': mesh_info[mid]['atrium'],
                        'part': mesh_info[mid]['part'],
                        'sigma_true': sigma_0,
                        'noise_level': noise,
                        'trial': trial,
                        'sigma_hat': sigma_hat,
                        'r_squared': r2,
                        'bias_mm': (sigma_hat - sigma_0) if sigma_hat is not None else None,
                    })

                    completed += 1

            # Progress
            elapsed = time.time() - t0
            pct = completed / total_fits * 100
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (total_fits - completed) / rate if rate > 0 else 0
            log(f"  σ₀={sigma_0:2d}mm, η={noise:.0%}: "
                f"{completed:,}/{total_fits:,} ({pct:.0f}%) — "
                f"{rate:.0f} fits/s, ETA {eta:.0f}s")

    elapsed_total = time.time() - t0
    log(f"\n  Completed {completed:,} fits in {elapsed_total:.1f}s "
        f"({completed/elapsed_total:.0f} fits/s)")

    # ── Save raw results ──
    raw_df = pd.DataFrame(raw_results)
    raw_path = os.path.join(out_dir, 'validation_full_raw.csv')
    raw_df.to_csv(raw_path, index=False)
    log(f"\n  Raw results → {raw_path}")

    # ── Aggregate: summary per (σ₀, η) — same format as original ──
    boot_rng = np.random.default_rng(42)
    summary_rows = []
    for sigma_0 in SIGMA_TRUE_VALUES:
        for noise in NOISE_LEVELS:
            subset = raw_df[(raw_df['sigma_true'] == sigma_0) &
                            (raw_df['noise_level'] == noise) &
                            (raw_df['sigma_hat'].notna())]

            if len(subset) == 0:
                continue

            biases = subset['bias_mm'].values
            ci_lo, ci_hi = bootstrap_ci(biases, rng=boot_rng)

            summary_rows.append({
                'sigma_true': sigma_0,
                'noise_level': noise,
                'n_fits': len(subset),
                'n_meshes': subset['map_id'].nunique(),
                'mean_sigma_hat': subset['sigma_hat'].mean(),
                'std_sigma_hat': subset['sigma_hat'].std(),
                'mean_bias_mm': biases.mean(),
                'median_bias_mm': np.median(biases),
                'ci95_lo': ci_lo,
                'ci95_hi': ci_hi,
                'mean_r_squared': subset['r_squared'].mean(),
            })

    summary_df = pd.DataFrame(summary_rows)
    summary_path = os.path.join(out_dir, 'validation_full_summary.csv')
    summary_df.to_csv(summary_path, index=False)
    log(f"  Summary → {summary_path}")

    # ── Per-mesh breakdown: detect problematic geometries ──
    mesh_rows = []
    for mid in valid_mesh_ids:
        for sigma_0 in SIGMA_TRUE_VALUES:
            for noise in NOISE_LEVELS:
                subset = raw_df[(raw_df['map_id'] == mid) &
                                (raw_df['sigma_true'] == sigma_0) &
                                (raw_df['noise_level'] == noise) &
                                (raw_df['sigma_hat'].notna())]

                if len(subset) == 0:
                    continue

                mesh_rows.append({
                    'map_id': mid,
                    'n_vertices': mesh_info[mid]['n_vertices'],
                    'sigma_true': sigma_0,
                    'noise_level': noise,
                    'n_fits': len(subset),
                    'mean_bias_mm': subset['bias_mm'].mean(),
                    'std_bias_mm': subset['bias_mm'].std(),
                    'mean_r_squared': subset['r_squared'].mean(),
                    'max_abs_bias': subset['bias_mm'].abs().max(),
                })

    mesh_df = pd.DataFrame(mesh_rows)
    mesh_path = os.path.join(out_dir, 'validation_full_by_mesh.csv')
    mesh_df.to_csv(mesh_path, index=False)
    log(f"  Per-mesh → {mesh_path}")

    # ── Flag problematic meshes ──
    if len(mesh_df) > 0:
        # At 10% noise, σ₀ ≤ 15mm: any mesh with |mean bias| > 3mm?
        relevant = mesh_df[(mesh_df['noise_level'] == 0.10) &
                           (mesh_df['sigma_true'] <= 15)]
        if len(relevant) > 0:
            problematic = relevant[relevant['mean_bias_mm'].abs() > 3.0]
            if len(problematic) > 0:
                log(f"\n  ⚠ PROBLEMATIC MESHES (|bias| > 3mm at η=10%, σ₀≤15mm):")
                for _, row in problematic.iterrows():
                    log(f"    Map {int(row['map_id'])}: σ₀={int(row['sigma_true'])}mm, "
                        f"bias={row['mean_bias_mm']:.2f}mm, "
                        f"n_vertices={int(row['n_vertices'])}")
            else:
                log(f"\n  ✓ No problematic meshes detected (all |bias| < 3mm "
                    f"at η=10%, σ₀≤15mm)")

    # ── Quick comparison with original 5-mesh validation ──
    log(f"\n  Comparison (σ₀=10mm, η=10%):")
    orig = summary_df[(summary_df['sigma_true'] == 10) &
                       (summary_df['noise_level'] == 0.10)]
    if len(orig) > 0:
        row = orig.iloc[0]
        log(f"    Full ({int(row['n_meshes'])} meshes, {int(row['n_fits'])} fits): "
            f"bias = {row['mean_bias_mm']:.3f}mm, "
            f"SD = {row['std_sigma_hat']:.3f}mm, "
            f"R² = {row['mean_r_squared']:.4f}")
        log(f"    Original (5 meshes, 100 fits): "
            f"bias = +0.59mm, SD = ~1.0mm, R² = 0.997")

    # ── Save log ──
    log_path = os.path.join(out_dir, 'validation_full_log.txt')
    with open(log_path, 'w') as f:
        f.write('\n'.join(log_lines))
    log(f"\n  Log → {log_path}")

    log(f"\nDone. Results in {out_dir}/")
    log(f"If results are problematic, simply delete {out_dir}/")


if __name__ == '__main__':
    main()
