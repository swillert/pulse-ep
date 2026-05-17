#!/usr/bin/env python3
"""Compare Gauss fit results with and without multifocal map exclusion."""

import os

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

DECAY_DIR = os.environ.get("PULSE_DECAY_DIR", "./decay_profiles_heat")
SUMMARY_CSV = os.path.join(DECAY_DIR, "decay_summary.csv")


def gauss_model(d, A, sigma, B):
    return A * np.exp(-(d**2) / (2 * sigma**2)) + B


def fit_map(map_id, bin_width=2.0, max_dist=40.0):
    csv_path = os.path.join(DECAY_DIR, f"decay_map_{map_id:03d}.csv")
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["geodesic_dist_mm", "matching_score_pct"])
    df = df[df["geodesic_dist_mm"] <= max_dist]
    if len(df) < 20:
        return None
    df["bin"] = (df["geodesic_dist_mm"] // bin_width) * bin_width + bin_width / 2
    binned = (
        df.groupby("bin")
        .agg(mean_score=("matching_score_pct", "mean"), count=("matching_score_pct", "count"))
        .reset_index()
    )
    binned = binned[binned["count"] >= 3]
    if len(binned) < 4:
        return None
    x = binned["bin"].values
    y = binned["mean_score"].values
    try:
        p0 = [y.max() - y.min(), 10.0, y.min()]
        bounds = ([0, 0.1, 0], [100, 40, 100])
        popt, _ = curve_fit(gauss_model, x, y, p0=p0, bounds=bounds, maxfev=10000)
        A, sigma, B = popt
        y_pred = gauss_model(x, *popt)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        return {
            "sigma": sigma,
            "A": A,
            "B": B,
            "R2": r2,
            "n_bins": len(binned),
            "n_vertices": len(df),
        }
    except Exception as e:
        return {
            "sigma": np.nan,
            "A": np.nan,
            "B": np.nan,
            "R2": np.nan,
            "n_bins": len(binned),
            "n_vertices": len(df),
            "error": str(e),
        }


summary = pd.read_csv(SUMMARY_CSV)
summary = summary[summary["max_geodesic_dist"].astype(float) >= 5.0].copy()
print(f"Total maps after fragment exclusion: {len(summary)}")
print(f"Multifocal maps: {summary['is_multifocal'].sum()}")
print()

results = []
for _, row in summary.iterrows():
    mid = row["map_id"]
    fit = fit_map(mid)
    if fit is None:
        continue
    fit["map_id"] = mid
    fit["atrium"] = row["atrium"]
    fit["part"] = row["part"]
    fit["ref_catheters"] = row["ref_catheters"]
    fit["is_multifocal"] = row["is_multifocal"]
    fit["focality_pct"] = float(row["focality_pct"])
    if row["atrium"] == "LA" and "posterior" in row["part"]:
        fit["region"] = "LA post"
    elif row["atrium"] == "LA" and "anterior" in row["part"]:
        fit["region"] = "LA ant"
    elif row["atrium"] == "RA" and "posterior" in row["part"]:
        fit["region"] = "RA post"
    elif row["atrium"] == "RA" and "lateral" in row["part"]:
        fit["region"] = "RA lat"
    else:
        fit["region"] = f"{row['atrium']} {row['part']}"
    results.append(fit)

rdf = pd.DataFrame(results)
print(f"Successfully fitted: {len(rdf)} maps")
print(f"  of which multifocal: {rdf['is_multifocal'].sum()}")
print()

print("=" * 80)
print("MULTIFOCAL MAPS — Fit results:")
print("=" * 80)
mf = rdf[rdf["is_multifocal"] == True]  # noqa: E712
for _, row in mf.iterrows():
    print(
        f"  Map {row['map_id']:3d} | {row['region']:8s} | ref={row['ref_catheters']} | "
        f"focal={row['focality_pct']:.0f}% | sigma={row['sigma']:.1f}mm | R2={row['R2']:.3f}"
    )
print()

print("=" * 80)
print("COMPARISON: With vs Without multifocal exclusion")
print("=" * 80)
ref_labels = {1: "SC", 2: "DC"}
regions = ["LA post", "LA ant", "RA post", "RA lat"]
for ref in [1, 2]:
    print(f"\n--- {ref_labels[ref]} ---")
    for region in regions:
        mask_base = (rdf["region"] == region) & (rdf["ref_catheters"] == ref)
        all_maps = rdf[mask_base]
        focal_maps = rdf[mask_base & (rdf["is_multifocal"] == False)]  # noqa: E712
        n_all = len(all_maps)
        n_focal = len(focal_maps)
        n_excluded = n_all - n_focal
        if n_all == 0:
            continue
        sigma_all = all_maps["sigma"].dropna()
        sigma_focal = focal_maps["sigma"].dropna()
        med_all = sigma_all.median() if len(sigma_all) > 0 else float("nan")
        q1_all = sigma_all.quantile(0.25) if len(sigma_all) > 0 else float("nan")
        q3_all = sigma_all.quantile(0.75) if len(sigma_all) > 0 else float("nan")
        med_focal = sigma_focal.median() if len(sigma_focal) > 0 else float("nan")
        q1_focal = sigma_focal.quantile(0.25) if len(sigma_focal) > 0 else float("nan")
        q3_focal = sigma_focal.quantile(0.75) if len(sigma_focal) > 0 else float("nan")
        print(
            f"  {region:8s} | n={n_all}->{n_focal} (excl {n_excluded}) | "
            f"ALL: sigma={med_all:.1f} [{q1_all:.1f};{q3_all:.1f}] | "
            f"FOCAL: sigma={med_focal:.1f} [{q1_focal:.1f};{q3_focal:.1f}] | "
            f"delta={med_all - med_focal:+.1f}mm"
        )

print()
print("=" * 80)
print("R2 of multifocal maps vs focal maps")
print("=" * 80)
mf_r2 = rdf[rdf["is_multifocal"] == True]["R2"]  # noqa: E712
focal_r2 = rdf[rdf["is_multifocal"] == False]["R2"]  # noqa: E712
print(
    f"  Multifocal (n={len(mf_r2)}): R2 median={mf_r2.median():.3f} [{mf_r2.min():.3f}; {mf_r2.max():.3f}]"
)
print(
    f"  Focal      (n={len(focal_r2)}): R2 median={focal_r2.median():.3f} [{focal_r2.min():.3f}; {focal_r2.max():.3f}]"
)

from scipy.stats import mannwhitneyu  # noqa: E402

print()
print("=" * 80)
print("Mann-Whitney U tests: SC vs DC per region")
print("=" * 80)
for region in regions:
    sc_all = rdf[(rdf["region"] == region) & (rdf["ref_catheters"] == 1)]["sigma"].dropna()
    dc_all = rdf[(rdf["region"] == region) & (rdf["ref_catheters"] == 2)]["sigma"].dropna()
    sc_focal = rdf[
        (rdf["region"] == region) & (rdf["ref_catheters"] == 1) & (rdf["is_multifocal"] == False)  # noqa: E712
    ]["sigma"].dropna()
    dc_focal = rdf[
        (rdf["region"] == region) & (rdf["ref_catheters"] == 2) & (rdf["is_multifocal"] == False)  # noqa: E712
    ]["sigma"].dropna()
    if len(sc_all) >= 2 and len(dc_all) >= 2:
        stat_all, p_all = mannwhitneyu(sc_all, dc_all, alternative="greater")
        if len(sc_focal) >= 2 and len(dc_focal) >= 2:
            stat_focal, p_focal = mannwhitneyu(sc_focal, dc_focal, alternative="greater")
        else:
            stat_focal, p_focal = 0, 1
        print(
            f"  {region:8s} | ALL: U={stat_all:.0f}, p={p_all:.4f} (n={len(sc_all)}v{len(dc_all)}) | "
            f"FOCAL: U={stat_focal:.0f}, p={p_focal:.4f} (n={len(sc_focal)}v{len(dc_focal)})"
        )
