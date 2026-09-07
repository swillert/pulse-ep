"""Versioned export of stored analysis data; no rendering transformations."""

import math
from dataclasses import asdict

import numpy as np


def json_safe(value):
    """Keep array positions and turn non-finite numbers into JSON null."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def raw_mesh(ep_map, scalar_name=None):
    name = scalar_name or ep_map.primary_scalar()
    values = ep_map.get_scalar(name) if name else []
    points = ep_map.measurement_points
    coordinates = [p.position for p in points] if points else ep_map.xyz
    return json_safe(
        {
            "schema_version": "1.0",
            "representation": "raw",
            "scalar_name": name,
            "processing": {
                "basis": "stored importer-conditioned data",
                "operations": [],
                "distance_applied": False,
                "nonfinite": "null",
            },
            "units": {"coordinates": "mm", "triangle_areas": "mm^2"},
            "index_base": 0,
            "map": {
                "name": ep_map.map_name,
                "study_name": ep_map.study_name,
                "number_of_points": ep_map.number_of_points,
                "mesh_file": ep_map.mesh_file,
                "attributes": ep_map.attributes,
            },
            "mesh_data": {
                "vertices": ep_map.vertices,
                "faces": ep_map.triangles,
                "scalar_data": values,
                "normalized_scalar_data": [],
                "scalar_fields": {n: f.to_dict() for n, f in ep_map.scalar_fields.items()},
                **{
                    n: getattr(ep_map, n)
                    for n in (
                        "triangle_areas",
                        "normals",
                        "is_vertex_at_edge",
                        "act_bip",
                        "uni_imp_frc",
                    )
                },
            },
            "point_data": {
                "coordinates": coordinates if coordinates is not None else [],
                "scalar_data": [p.get(name) for p in points],
                "normalized_scalar_data": [],
                "measurement_points": [asdict(p) for p in points],
                "legacy_coordinates": ep_map.xyz,
            },
        }
    )


def row_data(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def export_map(session, model, scalar_name=None):
    from pulse_ep.core.models import EPMapAttributes, PlacedPointModel, WaveformModel

    data = raw_mesh(model.to_epmap(include_points=True), scalar_name)
    attrs = session.query(EPMapAttributes).filter_by(map_id=model.id).first()
    data["map"].update(
        id=model.id, study_id=model.study_id, attributes=attrs.attributes if attrs else {}
    )
    data["study"] = row_data(model.study)
    data["point_data"]["legacy_points"] = [row_data(p) for p in model.points]
    data["placed_points"] = [
        row_data(p)
        for p in session.query(PlacedPointModel)
        .filter_by(study_id=model.study_id)
        .order_by(PlacedPointModel.id)
    ]
    waves = (
        session.query(WaveformModel)
        .filter(
            (WaveformModel.map_id == model.id)
            | ((WaveformModel.study_id == model.study_id) & WaveformModel.map_id.is_(None))
        )
        .order_by(WaveformModel.id)
    )
    data["waveforms"] = [
        {**row_data(w), "download_url": f"/waveforms/{w.id}/download"} for w in waves
    ]
    return json_safe(data)
