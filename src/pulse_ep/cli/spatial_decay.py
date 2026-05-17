#!/usr/bin/env python3
"""
Spatial Decay Profile for Pacemapping Maps.

For each pacemap in the database:
  1. Load mesh (vertices, triangles, act_bip)
  2. Matching score = abs(act_bip[:, 0]) per vertex
  3. Origin = vertex with highest matching score
  4. Geodesic distance from origin to every other vertex (Dijkstra on mesh graph)
  5. Export per-vertex CSV + summary CSV
"""

import os
import csv
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import shortest_path, connected_components
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel, EPMapAttributes, EPMapPoint


def build_adjacency_matrix(vertices, triangles):
    """Build sparse adjacency matrix with Euclidean edge weights from a triangle mesh."""
    n_verts = len(vertices)
    adj = lil_matrix((n_verts, n_verts), dtype=np.float64)

    for tri in triangles:
        for i in range(3):
            v0 = tri[i]
            v1 = tri[(i + 1) % 3]
            dist = np.linalg.norm(vertices[v0] - vertices[v1])
            if adj[v0, v1] == 0 or dist < adj[v0, v1]:
                adj[v0, v1] = dist
                adj[v1, v0] = dist

    return adj.tocsr()


def compute_geodesic_distances(adj, origin_idx):
    """Compute geodesic distances from origin vertex using Dijkstra."""
    distances = shortest_path(adj, method='D', directed=False, indices=origin_idx)
    return distances


def project_points_to_mesh(point_xyz, mesh_vertices):
    """Find the nearest mesh vertex for each measurement point.
    Returns array of vertex indices."""
    from scipy.spatial import cKDTree
    tree = cKDTree(mesh_vertices)
    _, indices = tree.query(point_xyz)
    return indices


def compute_cs_distance(session, map_id, point_xyz):
    """Compute CS-catheter to mapping-region distance for a single-ref map.

    Only valid for single-chamber reference where all 10 CS electrodes
    belong to one physical catheter in the coronary sinus.

    Returns dict with:
        region_centroid:  [x, y, z] of measurement point centroid
        cs_centroid:      [x, y, z] mean of all 10 CS electrodes across points
        cs_distance_mm:   Euclidean dist region ↔ cs_centroid  (mm)
        n_points_with_cs:  number of points that had CS positions
    or None if insufficient data.
    """
    cs_rows = (
        session.query(EPMapPoint.cs_positions)
        .filter(EPMapPoint.map_id == map_id, EPMapPoint.cs_positions != None)
        .all()
    )
    if not cs_rows or point_xyz is None or len(point_xyz) == 0:
        return None

    # Collect all CS electrode positions across measurement points
    all_electrodes = []
    for (cs_pos,) in cs_rows:
        arr = np.array(cs_pos).reshape(-1, 3)
        if len(arr) >= 10:
            all_electrodes.append(arr[:10])

    if not all_electrodes:
        return None

    cs_centroid = np.vstack(all_electrodes).mean(axis=0)
    region_centroid = point_xyz.mean(axis=0)

    return {
        'region_centroid': region_centroid,
        'cs_centroid': cs_centroid,
        'cs_distance_mm': float(np.linalg.norm(cs_centroid - region_centroid)),
        'n_points_with_cs': len(all_electrodes),
    }


def compute_focality(vertices, triangles, scores, percentile=95):
    """Compute focality of the high-score region.

    Returns dict with:
        n_clusters:       number of connected components in top-percentile region
        largest_cluster_pct:  fraction of top vertices in the largest component (0-100)
        n_top_vertices:   number of vertices above threshold
    """
    scores_clean = np.where(np.isnan(scores), 0.0, scores)
    threshold = np.percentile(scores_clean, percentile)
    top_mask = scores_clean >= threshold
    top_indices = set(np.where(top_mask)[0])
    n_top = len(top_indices)

    if n_top < 3:
        return {'n_clusters': 0, 'largest_cluster_pct': 0.0, 'n_top_vertices': n_top}

    # Build subgraph of top-percentile vertices connected by mesh edges
    idx_map = {v: i for i, v in enumerate(sorted(top_indices))}
    n_sub = len(idx_map)
    adj = lil_matrix((n_sub, n_sub), dtype=np.float64)

    for tri in triangles:
        if tri[0] in top_indices and tri[1] in top_indices and tri[2] in top_indices:
            for i in range(3):
                v0, v1 = tri[i], tri[(i + 1) % 3]
                i0, i1 = idx_map[v0], idx_map[v1]
                adj[i0, i1] = 1
                adj[i1, i0] = 1

    n_components, labels = connected_components(adj.tocsr(), directed=False)
    cluster_sizes = np.bincount(labels)
    largest_pct = float(cluster_sizes.max() / n_sub * 100) if n_components > 0 else 0.0

    return {
        'n_clusters': int(n_components),
        'largest_cluster_pct': largest_pct,
        'n_top_vertices': n_top,
    }


def process_pacemaps():
    output_dir = './decay_profiles'
    os.makedirs(output_dir, exist_ok=True)

    summary_rows = []

    with get_db_session() as session:
        # Find all pacemap EPMaps with atrium and part set
        pacemap_entries = (
            session.query(EPMapModel, EPMapAttributes)
            .join(EPMapAttributes, EPMapAttributes.map_id == EPMapModel.id)
            .filter(EPMapAttributes.attributes['pacemap'].astext.cast(
                __import__('sqlalchemy').Boolean) == True)
            .all()
        )

        # Filter for atrium and part being non-empty
        filtered = []
        for epmap, attrs in pacemap_entries:
            a = attrs.attributes or {}
            atrium = a.get('atrium', '')
            part = a.get('part', '')
            if atrium and part:
                filtered.append((epmap, attrs))

        print(f"Found {len(filtered)} pacemap(s) with atrium + part set.")

        for epmap, attrs in filtered:
            map_id = epmap.id
            map_name = epmap.map_name
            a = attrs.attributes or {}
            atrium = a.get('atrium', '')
            part = a.get('part', '')
            ref_catheters = a.get('reference_electrodes', 0)

            print(f"\nProcessing map {map_id}: {map_name} ({atrium}, {part})")

            # Load mesh arrays
            vertices = np.array(epmap.vertices).reshape(-1, 3)
            triangles = np.array(epmap.triangles).reshape(-1, 3)
            act_bip = np.array(epmap.act_bip).reshape(-1, 2)
            n_vertices = len(vertices)

            # Load real measurement point positions from ep_map_points
            point_rows = (session.query(
                EPMapPoint.point_index,
                EPMapPoint.position_x, EPMapPoint.position_y, EPMapPoint.position_z,
                EPMapPoint.unipolar_voltage, EPMapPoint.bipolar_voltage,
            ).filter(EPMapPoint.map_id == map_id)
             .order_by(EPMapPoint.point_index).all())

            has_points = len(point_rows) > 0 and point_rows[0][1] is not None

            # Matching score = abs(activation time column) per vertex
            matching_score = np.abs(act_bip[:, 0])
            score_clean = np.where(np.isnan(matching_score), 0.0, matching_score)
            origin_idx = int(np.argmax(score_clean))
            origin_score = score_clean[origin_idx]
            origin_xyz = vertices[origin_idx]

            # Focality check
            focality = compute_focality(vertices, triangles, matching_score)
            print(f"  Vertices: {n_vertices}, Points: {len(point_rows)}, "
                  f"Origin: {origin_idx} (score={origin_score:.1f}), "
                  f"Focality: {focality['largest_cluster_pct']:.0f}% "
                  f"({focality['n_clusters']} clusters)")

            is_multifocal = focality['largest_cluster_pct'] < 70.0
            if is_multifocal:
                print(f"  ⚠️  MULTIFOCAL — excluded from decay analysis")

            # Build adjacency and compute geodesic distances
            print("  Building adjacency matrix...")
            adj = build_adjacency_matrix(vertices, triangles)
            print("  Computing geodesic distances (Dijkstra)...")
            geo_dist = compute_geodesic_distances(adj, origin_idx)

            max_geodesic = np.nanmax(geo_dist[np.isfinite(geo_dist)]) if np.any(np.isfinite(geo_dist)) else 0.0

            # ── Per-vertex CSV (as before) ──
            csv_path = os.path.join(output_dir, f'decay_map_{map_id:03d}.csv')
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['vertex_idx', 'geodesic_dist_mm', 'matching_score_pct', 'x', 'y', 'z'])
                for vi in range(n_vertices):
                    gd = geo_dist[vi] if np.isfinite(geo_dist[vi]) else ''
                    ms = matching_score[vi] if not np.isnan(matching_score[vi]) else ''
                    writer.writerow([
                        vi,
                        f'{gd:.2f}' if isinstance(gd, float) else gd,
                        f'{ms:.1f}' if isinstance(ms, float) else ms,
                        f'{vertices[vi, 0]:.4f}',
                        f'{vertices[vi, 1]:.4f}',
                        f'{vertices[vi, 2]:.4f}',
                    ])
            print(f"  Written: {csv_path}")

            # ── Per-measurement-point CSV (NEW: real positions + geodesic dist) ──
            n_points_with_geo = 0
            if has_points:
                point_xyz = np.array([[r[1], r[2], r[3]] for r in point_rows])
                # Project each real point to nearest mesh vertex
                nearest_vertex = project_points_to_mesh(point_xyz, vertices)
                # Geodesic dist for each point = dist of its nearest vertex
                point_geo_dist = geo_dist[nearest_vertex]

                pts_csv = os.path.join(output_dir, f'decay_points_{map_id:03d}.csv')
                with open(pts_csv, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['point_index', 'x', 'y', 'z',
                                     'nearest_vertex', 'geodesic_dist_mm',
                                     'vertex_matching_score_pct',
                                     'unipolar_mV', 'bipolar_mV'])
                    for i, row in enumerate(point_rows):
                        pidx, px, py, pz, uni_v, bip_v = row
                        nv = nearest_vertex[i]
                        gd = point_geo_dist[i]
                        vs = matching_score[nv] if not np.isnan(matching_score[nv]) else ''
                        writer.writerow([
                            pidx, f'{px:.4f}', f'{py:.4f}', f'{pz:.4f}',
                            nv,
                            f'{gd:.2f}' if np.isfinite(gd) else '',
                            f'{vs:.1f}' if isinstance(vs, float) else vs,
                            f'{uni_v:.4f}' if uni_v is not None else '',
                            f'{bip_v:.4f}' if bip_v is not None else '',
                        ])
                n_points_with_geo = int(np.sum(np.isfinite(point_geo_dist)))
                print(f"  Written: {pts_csv} ({n_points_with_geo} points with geodesic dist)")

            # ── CS-distance calculation (only valid for single-chamber ref) ──
            cs_info = None
            if has_points and ref_catheters == 1:
                cs_info = compute_cs_distance(session, map_id, point_xyz)
                if cs_info:
                    print(f"  CS distance: {cs_info['cs_distance_mm']:.1f} mm  "
                          f"(from {cs_info['n_points_with_cs']} points with CS)")
            elif ref_catheters == 2:
                print(f"  CS distance: skipped (double-chamber, positions invalid due to pinbox)")

            summary_rows.append({
                'map_id': map_id,
                'map_name': map_name,
                'atrium': atrium,
                'part': part,
                'ref_catheters': ref_catheters,
                'n_vertices': n_vertices,
                'n_points': len(point_rows),
                'n_points_with_geodesic': n_points_with_geo,
                'origin_idx': origin_idx,
                'origin_score': f'{origin_score:.1f}',
                'focality_pct': f"{focality['largest_cluster_pct']:.1f}",
                'n_clusters': focality['n_clusters'],
                'is_multifocal': is_multifocal,
                'origin_x': f'{origin_xyz[0]:.2f}',
                'origin_y': f'{origin_xyz[1]:.2f}',
                'origin_z': f'{origin_xyz[2]:.2f}',
                'max_geodesic_dist': f'{max_geodesic:.1f}',
                'cs_distance_mm': f"{cs_info['cs_distance_mm']:.2f}" if cs_info else '',
                'n_points_with_cs': cs_info['n_points_with_cs'] if cs_info else 0,
                'region_centroid_x': f"{cs_info['region_centroid'][0]:.2f}" if cs_info else '',
                'region_centroid_y': f"{cs_info['region_centroid'][1]:.2f}" if cs_info else '',
                'region_centroid_z': f"{cs_info['region_centroid'][2]:.2f}" if cs_info else '',
                'cs_centroid_x': f"{cs_info['cs_centroid'][0]:.2f}" if cs_info else '',
                'cs_centroid_y': f"{cs_info['cs_centroid'][1]:.2f}" if cs_info else '',
                'cs_centroid_z': f"{cs_info['cs_centroid'][2]:.2f}" if cs_info else '',
            })

    # Write summary CSV
    summary_path = os.path.join(output_dir, 'decay_summary.csv')
    with open(summary_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'map_id', 'map_name', 'atrium', 'part', 'ref_catheters',
            'n_vertices', 'n_points', 'n_points_with_geodesic',
            'origin_idx', 'origin_score',
            'focality_pct', 'n_clusters', 'is_multifocal',
            'origin_x', 'origin_y', 'origin_z', 'max_geodesic_dist',
            'cs_distance_mm', 'n_points_with_cs',
            'region_centroid_x', 'region_centroid_y', 'region_centroid_z',
            'cs_centroid_x', 'cs_centroid_y', 'cs_centroid_z',
        ])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\nSummary written: {summary_path}")
    print(f"Total maps processed: {len(summary_rows)}")


if __name__ == '__main__':
    process_pacemaps()
