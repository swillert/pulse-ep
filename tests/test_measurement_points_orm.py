"""MeasurementPoint <-> MeasurementPointModel (open measurements/electrodes JSON)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_points
from pulse_ep.core.models import MeasurementPointModel, measurement_points_to_models

_POINTS = (
    "x,y,z,locChA_x,locChA_y,locChA_z,pp,unipoleMaxPP,correctedLAT,force,snr,correlationCoefficient\n"
    "1,2,3, 1.1,2.1,3.1, 0.71,0.66,182.4, 12.5, 70.6, 0.16\n"
)


def test_serialise_to_model():
    pts = parse_ensite_points(_POINTS)
    (model,) = measurement_points_to_models(pts, map_id=5)
    assert model.map_id == 5
    assert model.position == [1.0, 2.0, 3.0]
    # measurements as an open JSON map keyed by kind name
    assert model.measurements["voltage_bipolar"] == {"value": 0.71, "kind": "voltage_bipolar", "unit": "mV"}
    assert model.measurements["correlation"]["value"] == 0.16
    assert model.measurements["contact_force"]["value"] == 12.5
    assert model.electrodes["A"] == [1.1, 2.1, 3.1]


def test_model_roundtrips_back_to_domain():
    pts = parse_ensite_points(_POINTS)
    (model,) = measurement_points_to_models(pts, map_id=5)
    back = model.to_measurement_point()

    np.testing.assert_array_equal(back.position, [1, 2, 3])
    assert back.get("voltage_bipolar") == 0.71
    assert back.get("activation_time") == 182.4
    assert back.measurements["activation_time"].kind == "activation_time"
    assert back.measurements["voltage_bipolar"].unit == "mV"
    np.testing.assert_allclose(back.electrodes["A"], [1.1, 2.1, 3.1])


def test_columns_are_open_json():
    # sanity: the model stores measurements/electrodes as plain JSON-able dicts
    (model,) = measurement_points_to_models(parse_ensite_points(_POINTS), map_id=1)
    assert isinstance(model.measurements, dict) and isinstance(model.electrodes, dict)
    assert isinstance(MeasurementPointModel.__table__.c.measurements.type.__class__, type)
