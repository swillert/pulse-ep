"""CLI exporter: pulse-ep EPMap → ParaView-compatible ``.vtu`` file.

Talks **directly** to the database via ``pulse_ep.core`` — no running
HTTP server required. Useful for one-off exports, batch jobs, or
archiving maps alongside published figures.

Example::

    python examples/paraview/export_to_vtk.py \\
        --map-id 25 \\
        --scalar-name act \\
        --output /tmp/map_25.vtu

Then open ``/tmp/map_25.vtu`` in ParaView.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pyvista as pv

from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel


def _argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export a pulse-ep EPMap (mesh + per-vertex scalar field) to a "
            "ParaView-readable .vtu file."
        )
    )
    parser.add_argument(
        "--map-id",
        type=int,
        required=True,
        help="Database ID of the EPMap to export.",
    )
    parser.add_argument(
        "--scalar-name",
        default=None,
        help=(
            "Quantity to attach to the mesh, e.g. voltage_bipolar or "
            "activation_time. Defaults to the map's own primary quantity, "
            "which differs between vendors — list a map's fields with "
            "GET /epmaps/<id>/scalars."
        ),
    )
    parser.add_argument(
        "--distance",
        type=float,
        default=5.0,
        help="Interpolation radius around catheter points in mm (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination file. Extension decides the format (.vtu / .vtp / .vtk).",
    )
    parser.add_argument(
        "--include-points",
        action="store_true",
        help=(
            "Also write the measurement points as a separate <output>.points.vtp "
            "file so you can overlay them in ParaView."
        ),
    )
    return parser


def _load_epmap(map_id: int):
    with get_db_session() as session:
        model = EPMapModel.retrieve(session, map_id)
        if model is None:
            raise SystemExit(f"EPMap with ID {map_id} not found in the database.")
        return model.to_epmap(include_points=True), model.study_name, model.map_name


def _mesh_payload(epmap, scalar_name: str | None, distance: float):
    # None means "whatever this map is about"; resolve it so the exported
    # arrays carry the real quantity name rather than a placeholder.
    scalar_name = scalar_name or epmap.primary_scalar()
    if scalar_name is None:
        raise SystemExit("This map carries no scalar fields.")
    payload = epmap.extract_mesh_data(scalar_name=scalar_name, distance=distance)
    vertices = np.asarray(payload["mesh_data"]["vertices"], dtype=np.float64)
    faces = np.asarray(payload["mesh_data"]["faces"], dtype=np.int64)
    scalars = np.asarray(
        [math.nan if v is None else float(v) for v in payload["mesh_data"]["scalar_data"]],
        dtype=np.float64,
    )
    normalized = np.asarray(
        [
            math.nan if v is None else float(v)
            for v in payload["mesh_data"]["normalized_scalar_data"]
        ],
        dtype=np.float64,
    )
    return vertices, faces, scalars, normalized, payload["point_data"], scalar_name


def _to_unstructured(vertices, faces, scalar_name, scalars, normalized) -> pv.UnstructuredGrid:
    # pyvista expects an [n, 4] connectivity array with the leading "3"
    # for each triangle.
    n_faces = faces.shape[0]
    cells = np.column_stack([np.full(n_faces, 3, dtype=np.int64), faces]).ravel()
    cell_types = np.full(n_faces, pv.CellType.TRIANGLE, dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells, cell_types, vertices)
    grid.point_data[scalar_name] = scalars
    grid.point_data[f"{scalar_name}_normalized"] = normalized
    return grid


def main(argv: list[str] | None = None) -> int:
    args = _argparser().parse_args(argv)

    epmap, study_name, map_name = _load_epmap(args.map_id)
    print(f"Loaded EPMap {args.map_id}: {study_name!r} / {map_name!r}")

    vertices, faces, scalars, normalized, point_payload, scalar_name = _mesh_payload(
        epmap, args.scalar_name, args.distance
    )
    print(f"Scalar: {scalar_name}")

    grid = _to_unstructured(vertices, faces, scalar_name, scalars, normalized)
    grid.field_data["study_name"] = np.array([study_name])
    grid.field_data["map_name"] = np.array([map_name])

    out: Path = args.output.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out)
    print(f"Wrote mesh ({grid.n_points} points, {grid.n_cells} cells) → {out}")

    if args.include_points:
        coords = np.asarray(point_payload["coordinates"], dtype=np.float64)
        if coords.size:
            cloud = pv.PolyData(coords)
            point_scalars = point_payload["scalar_data"] or []
            if point_scalars:
                cloud.point_data[scalar_name] = np.asarray(
                    [math.nan if v is None else float(v) for v in point_scalars],
                    dtype=np.float64,
                )
            points_out = out.with_suffix("").with_suffix(".points.vtp")
            cloud.save(points_out)
            print(f"Wrote {cloud.n_points} measurement points → {points_out}")
        else:
            print("No measurement points in payload — skipping --include-points.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
