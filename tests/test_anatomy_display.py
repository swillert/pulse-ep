"""Geometry-only EnSite anatomy must remain viewable without made-up scalars."""

import importlib

import numpy as np
import pytest
from flask_jwt_extended import create_access_token

from pulse_ep import EPMap


@pytest.fixture
def anatomy(synthetic_atrium_arrays):
    vertices, triangles, _ = synthetic_atrium_arrays
    return EPMap("Anatomy: LA", "synthetic", vertices=vertices, triangles=triangles)


@pytest.fixture
def client_and_headers(monkeypatch, anatomy):
    module = importlib.import_module("pulse_ep.server.app")
    monkeypatch.setattr(module, "get_epmap_from_db", lambda _: anatomy)
    monkeypatch.setitem(module.app.config, "JWT_SECRET_KEY", "synthetic-anatomy-key-" * 3)
    with module.app.app_context():
        token = create_access_token(identity="synthetic")
    return module.app.test_client(), {"Authorization": "Bearer " + token}


def test_anatomy_display_keeps_geometry_without_scalar_values(anatomy, client_and_headers):
    client, headers = client_and_headers
    before = anatomy.vertices.copy()
    response = client.get("/get_mesh_data?map_id=1", headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["scalar_name"] is None
    mesh = body["mesh_data"]
    assert len(mesh["vertices"]) > 0
    assert len(mesh["faces"]) > 0
    assert np.asarray(mesh["faces"]).max() < len(mesh["vertices"])
    assert mesh["scalar_data"] == []
    assert mesh["normalized_scalar_data"] == []
    assert body["point_data"]["coordinates"] == []
    assert anatomy.scalar_fields == {}
    np.testing.assert_array_equal(anatomy.vertices, before)


@pytest.mark.parametrize("scalar_name", [None, "voltage_bipolar"])
def test_anatomy_interval_analysis_returns_explanation(client_and_headers, scalar_name):
    client, headers = client_and_headers
    response = client.post(
        "/calculate_areas_for_intervals",
        json={"map_id": 1, "intervals": [[0, 1]], "scalar_name": scalar_name},
        headers=headers,
    )
    assert response.status_code == 400
    assert "scalar" in response.get_json()["error"].lower()


def test_anatomy_display_rejects_an_explicitly_requested_missing_field(client_and_headers):
    client, headers = client_and_headers
    response = client.get("/get_mesh_data?map_id=1&scalar_name=voltage_bipolar", headers=headers)
    assert response.status_code == 400
    assert "voltage_bipolar" in response.get_json()["error"]
