#!/usr/bin/env python3
"""Extract mesh geometry (vertices + triangles) for validation maps.

Run this ONCE on the machine holding the database; then copy the .npz files to
wherever the validation pipeline is executed.

Usage:
    python -m scripts.extract_meshes_for_validation

Output directory can be overridden via the PULSE_DECAY_DIR environment variable
(default: ./decay_profiles).
"""
import numpy as np
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel
import os

SELECTED = [75, 16, 35, 14, 64]
OUTPUT = os.environ.get('PULSE_DECAY_DIR', './decay_profiles')
os.makedirs(OUTPUT, exist_ok=True)

with get_db_session() as session:
    for mid in SELECTED:
        epmap = session.query(EPMapModel).filter_by(id=mid).first()
        if epmap is None:
            print(f"Map {mid} NOT FOUND")
            continue
        vertices = np.array(epmap.vertices).reshape(-1, 3)
        triangles = np.array(epmap.triangles).reshape(-1, 3)
        outpath = os.path.join(OUTPUT, f'mesh_{mid:03d}.npz')
        np.savez_compressed(outpath, vertices=vertices, triangles=triangles)
        print(f"Map {mid}: {len(vertices)} verts, {len(triangles)} tris → {outpath}")

print("Done. Now copy decay_profiles/mesh_*.npz to Claude if needed.")
