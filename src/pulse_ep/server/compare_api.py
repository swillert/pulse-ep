"""REST API for comparing two maps into a delta field (JWT-protected blueprint).

``POST /api/compare`` with ``{map_a_id, map_b_id, scalar_name, metric,
max_distance, include_delta}`` returns the per-``map_a``-vertex delta plus
summary stats. Comparison is an operation (not stored state); the caller can
keep the result as a derived map or a report.
"""

from __future__ import annotations

import numpy as np
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from pulse_ep.core.comparison import compare_maps
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapModel

compare_api = Blueprint("compare_api", __name__)


@compare_api.post("/api/compare")
@jwt_required()
def compare():
    data = request.get_json(silent=True) or {}
    try:
        a_id = int(data["map_a_id"])
        b_id = int(data["map_b_id"])
        scalar_name = data["scalar_name"]
    except (KeyError, TypeError, ValueError):
        return jsonify({"msg": "map_a_id, map_b_id and scalar_name are required"}), 400

    metric = data.get("metric", "euclidean")
    max_distance = data.get("max_distance")
    include_delta = bool(data.get("include_delta", True))

    with get_db_session() as session:
        map_a = session.get(EPMapModel, a_id)
        map_b = session.get(EPMapModel, b_id)
        if map_a is None or map_b is None:
            return jsonify({"msg": "map not found"}), 404
        try:
            result = compare_maps(
                map_a.to_epmap(), map_b.to_epmap(), scalar_name, metric, max_distance
            )
        except (ValueError, KeyError) as exc:
            return jsonify({"msg": str(exc)}), 400

    body = {
        "metric": result.metric,
        "scalar_name": result.scalar_name,
        "n_masked": result.n_masked,
        "stats": result.stats(),
    }
    if include_delta:
        # NaN is not valid JSON — masked / missing correspondences become null
        body["delta"] = [None if not np.isfinite(x) else float(x) for x in result.delta]
    return jsonify(body)
