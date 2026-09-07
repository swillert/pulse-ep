"""Persistence layer for vendor-neutral scalar fields + vendor/provenance.

The production schema uses PostgreSQL ARRAY/JSONB types, so
these tests exercise the pure (de)serialisation converters directly rather
than a live session.
"""

from __future__ import annotations

import numpy as np

from pulse_ep import EPMap, Study
from pulse_ep.core.models import EPMapModel, StudyModel
from pulse_ep.core.scalar_field import PACEMAP_SCORE, VOLTAGE_BIPOLAR, ScalarField


def test_scalar_field_dict_roundtrip() -> None:
    f = ScalarField(
        np.array([1.0, 2.0, np.nan]),
        VOLTAGE_BIPOLAR,
        status_mask=np.array([True, False, True]),
        source="ensite/6.0",
    )
    f2 = ScalarField.from_dict(f.to_dict())
    assert f2.kind == VOLTAGE_BIPOLAR and f2.unit == "mV" and f2.source == "ensite/6.0"
    np.testing.assert_array_equal(f2.values, f.values)
    np.testing.assert_array_equal(f2.status_mask, f.status_mask)


def test_scalar_field_dict_roundtrip_no_mask() -> None:
    f = ScalarField(np.array([90.0, 50.0]), PACEMAP_SCORE)
    f2 = ScalarField.from_dict(f.to_dict())
    assert f2.status_mask is None and f2.unit == "%"


def _mini_epmap(with_act_bip: bool) -> EPMap:
    verts = np.arange(15, dtype=float).reshape(5, 3)
    tris = np.array([[0, 1, 2], [2, 3, 4]])
    epmap = EPMap(
        map_name="m",
        study_name="s",
        vertices=verts,
        triangles=tris,
        triangle_areas=np.ones(2),
        is_vertex_at_edge=np.zeros(5, dtype=bool),
        normals=np.zeros((5, 3)),
        act_bip=(np.column_stack([np.arange(5.0), np.arange(5.0)]) if with_act_bip else None),
    )
    epmap.register_scalar("voltage_bipolar", np.linspace(0.1, 3.0, 5), kind=VOLTAGE_BIPOLAR)
    return epmap


def test_epmapmodel_roundtrip_preserves_scalar_fields() -> None:
    epmap = _mini_epmap(with_act_bip=True)
    model = EPMapModel.from_epmap(epmap, study_id=1)
    # serialised into the JSON column as a plain dict
    assert set(model.scalar_fields) == {"voltage_bipolar"}
    assert model.scalar_fields["voltage_bipolar"]["kind"] == VOLTAGE_BIPOLAR

    restored = model.to_epmap()
    field = restored.get_field("voltage_bipolar")
    assert field.kind == VOLTAGE_BIPOLAR and field.unit == "mV"
    np.testing.assert_allclose(restored.get_scalar("voltage_bipolar"), np.linspace(0.1, 3.0, 5))


def test_epmapmodel_roundtrip_without_act_bip() -> None:
    # EnSite-style: no act_bip, only registered fields — converters stay None-safe.
    epmap = _mini_epmap(with_act_bip=False)
    model = EPMapModel.from_epmap(epmap, study_id=1)
    assert model.act_bip is None
    restored = model.to_epmap()
    assert restored.act_bip is None
    np.testing.assert_allclose(restored.get_scalar("voltage_bipolar"), np.linspace(0.1, 3.0, 5))


def test_studymodel_carries_vendor_and_provenance() -> None:
    study = Study("s", vendor="ensite", provenance={"software_version": "6.0.0.683129"})
    sm = StudyModel.from_study(study)
    assert sm.vendor == "ensite"
    assert sm.provenance == {"software_version": "6.0.0.683129"}
