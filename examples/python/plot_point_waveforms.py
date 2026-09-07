"""Plot a CARTO acquisition point and its API-delivered electrograms.

Requires an imported map with opt-in waveforms. Credentials are read from
PULSE_EP_BASE_URL, PULSE_EP_USERNAME and PULSE_EP_PASSWORD. No clinical input
or downloaded signal arrays are written by this example. The exported figure
contains clinical signals and must be reviewed before public distribution.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
from urllib.parse import urljoin

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
import pyvista as pv
import requests


def retrieve(map_id: int, point_id: str):
    """Follow map -> source point -> waveform row -> authenticated Parquet."""
    base = os.environ["PULSE_EP_BASE_URL"].rstrip("/")
    with requests.Session() as client:
        response = client.post(
            base + "/login_user",
            json={
                "username": os.environ["PULSE_EP_USERNAME"],
                "password": os.environ["PULSE_EP_PASSWORD"],
            },
            timeout=30,
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        response = client.get(
            base + "/get_mesh_data",
            params={
                "map_id": map_id,
                "representation": "raw",
                "scalar_name": "voltage_bipolar",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        point = next(
            (
                p
                for p in payload["point_data"]["measurement_points"]
                if str(p["source_id"]) == point_id
            ),
            None,
        )
        if point is None:
            raise ValueError("The selected source point does not belong to this map")
        rows = [
            w
            for w in payload["waveforms"]
            if str(w.get("point_source_id")) == point_id and w.get("map_id") == map_id
        ]
        if len(rows) != 1:
            raise ValueError(f"Expected one waveform reference for the point, found {len(rows)}")
        response = client.get(urljoin(base + "/", rows[0]["download_url"]), timeout=60)
        response.raise_for_status()
        parquet_bytes = response.content
    table = pq.read_table(io.BytesIO(parquet_bytes))
    metadata = json.loads(table.schema.metadata[b"pulse_ep_waveform"])
    context = next((p for p in metadata["meta"]["points"] if str(p["point_id"]) == point_id), None)
    if context is None:
        raise ValueError("Waveform metadata has no matching point context")
    return payload, point, table, metadata, context, parquet_bytes


def make_figure(payload, point, table, metadata, context, output: Path, half_window_ms=250):
    """Draw stored mV values, with time relative to the reference annotation."""
    fs = float(metadata["sample_rate"])
    reference = context["annotations"]["reference"]
    if fs <= 0 or reference is None or metadata["meta"].get("gain_mv") is None:
        raise ValueError("Sampling, gain and reference annotation are required")
    time = np.arange(table.num_rows) * 1000 / fs - reference
    selected = np.abs(time) <= half_window_ms
    if selected.sum() < 2:
        raise ValueError("Requested interval contains fewer than two samples")
    channels = [
        (role, context["mapping_channels"][role]) for role in ("unipolar", "bipolar", "reference")
    ]
    if any(name not in table.column_names for _, name in channels):
        raise ValueError("An annotated channel is absent from the recording")

    vertices = np.asarray(payload["mesh_data"]["vertices"], dtype=float)
    faces = np.asarray(payload["mesh_data"]["faces"], dtype=int)
    position = np.asarray(point["position"], dtype=float)
    mesh = pv.PolyData(vertices, np.c_[np.full(len(faces), 3), faces])
    plot = pv.Plotter(off_screen=True, window_size=(1000, 850))
    plot.set_background("white")
    plot.add_mesh(mesh, color="#d4d9df", smooth_shading=True)
    centre = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    plot.camera_position = [centre + [0, 0, -700], centre, [0, 1, 0]]
    plot.enable_parallel_projection()
    plot.camera.parallel_scale = 62
    plot.add_text("PA | superior up", color="black", font_size=12)
    rendered = plot.screenshot()
    # Mark the projection of the original acquisition coordinate, including
    # points just inside the surface; do not snap or move it onto the mesh.
    plot.renderer.SetWorldPoint(*position, 1.0)
    plot.renderer.WorldToDisplay()
    screen_x, screen_y, _ = plot.renderer.GetDisplayPoint()
    plot.close()

    figure = plt.figure(figsize=(11, 4.8), layout="constrained")
    grid = figure.add_gridspec(3, 2, width_ratios=[1.12, 1])
    anatomy = figure.add_subplot(grid[:, 0])
    anatomy.imshow(rendered)
    projected = (screen_x, rendered.shape[0] - screen_y)
    anatomy.scatter(*projected, s=65, color="#c83232", edgecolor="white", linewidth=1)
    anatomy.annotate(
        "Selected point",
        projected,
        xytext=(22, 24),
        textcoords="offset points",
        color="#9b1c1c",
        fontsize=10,
        arrowprops={"arrowstyle": "-", "color": "#9b1c1c"},
    )
    anatomy.axis("off")
    anatomy.set_title(
        "A  Acquisition point on the CARTO mesh", loc="left", fontsize=11, weight="bold"
    )
    map_annotation = context["annotations"].get("map")
    for i, (role, name) in enumerate(channels):
        ax = figure.add_subplot(grid[i, 1])
        signal = table[name].to_numpy()
        ax.plot(time[selected], signal[selected], color="#214f71", linewidth=0.85)
        ax.axvline(0, color="#777777", linewidth=0.8, linestyle="--")
        if map_annotation is not None and abs(map_annotation - reference) <= half_window_ms:
            ax.axvline(map_annotation - reference, color="#bd6a22", linewidth=0.8, linestyle=":")
        ax.set_ylabel("mV")
        ax.set_xlim(-half_window_ms, half_window_ms)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.text(
            0.01,
            0.97,
            f"{role.capitalize()}: {name}",
            transform=ax.transAxes,
            va="top",
            fontsize=9,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
        if i == 0:
            ax.set_title("B  Point-linked electrograms", loc="left", fontsize=11, weight="bold")
        if i < 2:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel("Time relative to reference annotation (ms)")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=300)
    plt.close(figure)
    return {
        "recording_samples": table.num_rows,
        "recording_channels": len(metadata["channels"]),
        "sample_rate_hz": fs,
        "displayed_samples": int(selected.sum()),
        "display_half_window_ms": half_window_ms,
        "channels": dict(channels),
        "gain_mv_per_count": metadata["meta"]["gain_mv"],
        "map_annotation_relative_ms": None
        if map_annotation is None
        else map_annotation - reference,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-id", type=int, required=True)
    parser.add_argument(
        "--point-id", required=True, help="CARTO source point ID, not a mesh vertex index"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--half-window-ms", type=float, default=250)
    args = parser.parse_args()
    if args.half_window_ms <= 0:
        parser.error("--half-window-ms must be positive")
    payload, point, table, metadata, context, _ = retrieve(args.map_id, args.point_id)
    summary = make_figure(
        payload, point, table, metadata, context, args.output, args.half_window_ms
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
