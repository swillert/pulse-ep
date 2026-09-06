#!/usr/bin/env python3
"""Extract mesh geometry (vertices + triangles) for selected maps.

Writes one compressed ``mesh_<id>.npz`` per map, so a validation pipeline can
run somewhere other than the machine holding the database.

    pulse-ep-extract-meshes --maps 14 16 35 --output ./decay_profiles

Everything happens inside :func:`main`: importing this module must not touch
the database, in line with the project's lazy-initialisation rule.
"""

from __future__ import annotations

import argparse
import os

import numpy as np

DEFAULT_OUTPUT = os.environ.get("PULSE_DECAY_DIR", "./decay_profiles")


def extract_meshes(map_ids: list[int], output_dir: str) -> list[str]:
    """Write ``mesh_<id>.npz`` for each map id; return the paths written."""
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import EPMapModel

    os.makedirs(output_dir, exist_ok=True)
    written: list[str] = []
    with get_db_session() as session:
        for mid in map_ids:
            epmap = session.query(EPMapModel).filter_by(id=mid).first()
            if epmap is None:
                print(f"Map {mid} NOT FOUND")
                continue
            vertices = np.array(epmap.vertices).reshape(-1, 3)
            triangles = np.array(epmap.triangles).reshape(-1, 3)
            outpath = os.path.join(output_dir, f"mesh_{mid:03d}.npz")
            np.savez_compressed(outpath, vertices=vertices, triangles=triangles)
            print(f"Map {mid}: {len(vertices)} verts, {len(triangles)} tris -> {outpath}")
            written.append(outpath)
    return written


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-extract-meshes",
        description="Extract mesh geometry for selected maps as .npz files.",
    )
    p.add_argument(
        "--maps",
        "-m",
        type=int,
        nargs="+",
        required=True,
        metavar="ID",
        help="Map ids to extract (see /list_epmaps_in_study or the database).",
    )
    p.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        metavar="DIR",
        help="Output directory (default: %(default)s, or $PULSE_DECAY_DIR).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    written = extract_meshes(args.maps, args.output)
    print(f"Done. {len(written)} mesh file(s) written to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
