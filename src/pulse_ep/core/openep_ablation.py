"""Explicitly selected RF markers in OpenEP's automatic-tag container."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.placed_point import ABLATION


def ablation_arrays(points):
    selected = [p for p in points if p.type == ABLATION and np.isfinite(p.position).all()]

    def values(key):
        result = []
        for point in selected:
            value = point.attributes.get(key)
            try:
                result.append(float(value) if value is not None else np.nan)
            except (TypeError, ValueError):
                result.append(np.nan)
        return np.asarray(result, float)

    # An instantaneous/average power is not silently relabelled maximum power.
    tag = {
        "X": np.array([p.position for p in selected], float).reshape(-1, 3),
        "time": values("duration_s"),
        "avgForce": values("average_force_g"),
        "maxTemp": values("max_temperature_c"),
        "maxPower": values("max_power_w"),
        "Impedance": {
            "baseImp": values("base_impedance_ohm"),
            "impDrop": values("impedance_drop_ohm"),
        },
        "fti": values("force_time_integral"),
    }
    # Keep index families separate. A CARTO ablation index and another vendor's
    # lesion index must never become one unnamed numeric vector.
    indices = [
        {"name": key, "value": values(key)}
        for key in ("rf_index", "ablation_index", "lesion_index")
        if any(key in p.attributes for p in selected)
    ]
    tag["index"] = (
        indices[0] if len(indices) == 1 else {"name": "", "value": np.full(len(selected), np.nan)}
    )
    metadata = {
        "source_ids": [p.source_id or "" for p in selected],
        "attributes": [dict(p.attributes) for p in selected],
        "indices": indices,
        "time_unit": "s",
        "time_kind": "duration",
    }
    notes = [
        f"ablation: {len(selected)} explicitly selected RF markers; no automatic assignment to this map"
    ]
    if len(selected) != len(points):
        notes.append(
            "ablation: non-RF markers (including PFA) and invalid positions excluded from rfindex"
        )
    return {"name": "pulse-ep RF markers", "tag": tag}, metadata, notes
