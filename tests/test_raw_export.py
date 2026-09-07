"""Raw exports must retain topology, precision, missing positions and semantics."""

import importlib
import json
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest
from flask_jwt_extended import create_access_token

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.server.raw_export import json_safe, raw_mesh


def test_raw_export_preserves_all_arrays_and_point_metadata():
    points = [MeasurementPoint(np.array([0.0, 2.0, 3.0]), source_id="p1", index=0)]
    points[0].add("novel", 4.0, "unknown", "u")
    points[0].electrodes["E1"] = np.array([0.0, 0.0, 1.0])
    ep = EPMap(
        "test",
        "study",
        vertices=np.array([[0.0, 0.0, 0.0], [1.123456789123, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        triangles=np.array([[0, 1, 2]]),
        measurement_points=points,
        attributes={"chamber": "left"},
    )
    ep.register_scalar(
        "novel",
        np.array([1.123456789123, np.nan, np.inf]),
        "unknown",
        unit="u",
        status_mask=np.array([True, False, False]),
        source="fixture",
    )
    before = ep.vertices.copy()
    data = raw_mesh(ep)
    json.dumps(data, allow_nan=False)
    assert data["mesh_data"]["scalar_fields"]["novel"] == {
        "values": [1.123456789123, None, None],
        "kind": "unknown",
        "unit": "u",
        "status_mask": [True, False, False],
        "source": "fixture",
    }
    assert data["point_data"]["measurement_points"] == json_safe([asdict(p) for p in points])
    assert data["mesh_data"]["faces"] == [[0, 1, 2]]
    assert data["mesh_data"]["vertices"] == before.tolist()
    assert data["processing"]["operations"] == []
    assert ep.pv_mesh is None
    np.testing.assert_array_equal(ep.vertices, before)


def test_anatomy_only_export_and_invalid_field():
    ep = EPMap("anatomy", "study", vertices=np.empty((0, 3)), triangles=np.empty((0, 3), int))
    data = raw_mesh(ep)
    assert data["scalar_name"] is None
    assert data["point_data"]["coordinates"] == []
    assert data["mesh_data"]["scalar_fields"] == {}
    with pytest.raises(ValueError):
        raw_mesh(ep, "not-present")


def test_legacy_zero_coordinates_survive_database_conversion():
    from pulse_ep.core.models import EPMapModel, EPMapPoint

    model = EPMapModel("old", 1, study_name="study")
    model.points = [EPMapPoint(point_index=0, position_x=0.0, position_y=0.0, position_z=None)]
    ep = model.to_epmap(include_points=True)
    np.testing.assert_array_equal(ep.xyz, [[0.0, 0.0, np.nan]])


def test_route_validation_and_authentication(monkeypatch):
    module = importlib.import_module("pulse_ep.server.app")
    monkeypatch.setitem(module.app.config, "JWT_SECRET_KEY", "synthetic-only-test-key-" * 3)
    with module.app.app_context():
        token = create_access_token(identity="synthetic")
    client = module.app.test_client()
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/get_mesh_data?representation=raw&map_id=1").status_code == 401
    assert client.get("/get_mesh_data?representation=unknown", headers=headers).status_code == 400
    assert (
        client.get("/get_mesh_data?representation=raw&map_id=no", headers=headers).status_code
        == 400
    )
    assert client.get("/waveforms/1/download").status_code == 401


def test_waveform_download_is_confined_to_store(monkeypatch, tmp_path):
    module = importlib.import_module("pulse_ep.server.app")
    root = tmp_path / "store"
    root.mkdir()
    (tmp_path / "outside.parquet").write_bytes(b"private")
    (root / "signal.parquet").write_bytes(b"test-samples")
    row = SimpleNamespace(data_uri="../outside.parquet")

    class Query:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return row

    @contextmanager
    def session():
        yield SimpleNamespace(query=lambda _: Query())

    monkeypatch.setattr(module, "get_db_session", session)
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(waveform_store_dir=str(root))
    )
    monkeypatch.setitem(module.app.config, "JWT_SECRET_KEY", "synthetic-only-test-key-" * 3)
    with module.app.app_context():
        token = create_access_token(identity="synthetic")
    headers = {"Authorization": "Bearer " + token}
    client = module.app.test_client()
    assert client.get("/waveforms/1/download", headers=headers).status_code == 404
    row.data_uri = "signal.parquet"
    response = client.get("/waveforms/1/download", headers=headers)
    assert response.status_code == 200
    assert response.data == b"test-samples"
