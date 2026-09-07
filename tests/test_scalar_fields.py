"""Vendor-neutral scalar-field layer on :class:`pulse_ep.EPMap`.

Proves the Phase-0 refactor:

1. The legacy CARTO ``act_bip`` bridge still resolves as before
   (``"act"`` → column 0 with sign-normalisation, ``"vol"`` → column 1).
2. A map carrying only registered ``scalar_fields`` (as an EnSite X voltage
   mesh would) flows through the same analysis methods.
3. ``kind`` is declared at registration and conditioning (activation
   sign-flip, sentinel masking) happens once, at import.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from pulse_ep import EPMap
from pulse_ep.core.importers.carto import register_carto_scalars
from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    PACEMAP_SCORE,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
    ScalarField,
)
from pulse_ep.examples.demo_synthetic import (
    gaussian_score_field,
    make_synthetic_atrium,
)


def test_missing_scalar_values_round_trip_through_strict_json():
    field = ScalarField(
        np.array([1.25, np.nan, np.inf, -np.inf]),
        VOLTAGE_BIPOLAR,
        status_mask=np.array([True, False, False, False]),
        source="synthetic",
    )
    # This must also be valid for PostgreSQL JSONB, which rejects NaN tokens.
    encoded = json.dumps(field.to_dict(), allow_nan=False)
    payload = json.loads(encoded)
    assert payload["values"] == [1.25, None, None, None]
    restored = ScalarField.from_dict(payload)
    np.testing.assert_allclose(restored.values, [1.25, np.nan, np.nan, np.nan])
    np.testing.assert_array_equal(restored.status_mask, field.status_mask)
    assert restored.unit == "mV" and restored.source == "synthetic"


@pytest.fixture
def carto_like_map():
    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    voltage = scores / 100.0  # stand-in second column
    act_bip = np.column_stack([scores, voltage])
    epmap = EPMap(
        map_name="carto",
        study_name="s",
        vertices=vertices,
        triangles=triangles,
        xyz=vertices.copy(),  # measurements sit on the vertices
        act_bip=act_bip,
    )
    # what CartoImporter does at import: register neutral scalar fields
    register_carto_scalars(epmap, act_bip)
    return epmap


@pytest.fixture
def ensite_like_map():
    """Voltage-only map: no ``act_bip``, one registered scalar field."""
    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    voltage = 0.05 + scores / 100.0 * 3.0  # mV-like, strictly positive
    epmap = EPMap(
        map_name="ensite",
        study_name="s",
        vertices=vertices,
        triangles=triangles,
        xyz=vertices.copy(),
    )
    epmap.register_scalar("voltage_bipolar", voltage, kind=VOLTAGE_BIPOLAR)
    return epmap


# --- resolver: CARTO scalars come from registered fields -----------------


def test_carto_registers_scalars_under_the_quantity_name(carto_like_map) -> None:
    """CARTO's fields carry the same names EnSite X uses, so one query spans
    both vendors — they used to be CARTO-only ``act``/``vol``."""
    # Positive scores → activation_time (no flip)
    np.testing.assert_array_equal(
        carto_like_map.get_scalar("activation_time"), carto_like_map.act_bip[:, 0]
    )
    np.testing.assert_array_equal(
        carto_like_map.get_scalar("voltage_bipolar"), carto_like_map.act_bip[:, 1]
    )
    assert carto_like_map.get_field("activation_time").kind == ACTIVATION_TIME
    assert "act" not in carto_like_map.scalar_fields


def test_legacy_carto_names_still_resolve(carto_like_map) -> None:
    """Studies imported before the rename, and clients still asking for
    ``act``/``vol``, must keep working."""
    np.testing.assert_array_equal(
        carto_like_map.get_scalar("act"), carto_like_map.get_scalar("activation_time")
    )
    np.testing.assert_array_equal(
        carto_like_map.get_scalar("vol"), carto_like_map.get_scalar("voltage_bipolar")
    )


def test_legacy_act_resolves_to_whichever_quantity_the_map_holds() -> None:
    """``act`` was overloaded — activation time *or* pace-mapping score."""
    from pulse_ep.core.scalar_field import PACEMAP_SCORE

    m = EPMap(map_name="pacemap", study_name="s")
    m.register_scalar("pacemap_score", np.array([80.0, 90.0]), kind=PACEMAP_SCORE)
    np.testing.assert_array_equal(m.get_scalar("act"), [80.0, 90.0])


def test_field_of_kind_finds_a_field_under_any_name() -> None:
    m = EPMap(map_name="m", study_name="s")
    m.register_scalar("some_vendor_token", np.array([1.0]), kind=ACTIVATION_TIME)
    assert m.field_of_kind(ACTIVATION_TIME) is not None
    assert m.field_of_kind("voltage_bipolar") is None


def test_get_scalar_prefers_registered_field(ensite_like_map) -> None:
    np.testing.assert_array_equal(
        ensite_like_map.get_scalar("voltage_bipolar"),
        ensite_like_map.get_field("voltage_bipolar").values,
    )


def test_get_scalar_unknown_raises(ensite_like_map) -> None:
    with pytest.raises(ValueError, match="Unsupported scalar_name"):
        ensite_like_map.get_scalar("does_not_exist")


def test_register_scalar_overwrites(carto_like_map) -> None:
    override = np.full(carto_like_map.vertices.shape[0], 7.0)
    carto_like_map.register_scalar("act", override, kind=PACEMAP_SCORE)
    np.testing.assert_array_equal(carto_like_map.get_scalar("act"), override)


# --- kind + import-time conditioning -------------------------------------


def test_field_carries_kind_and_unit(ensite_like_map) -> None:
    field = ensite_like_map.get_field("voltage_bipolar")
    assert field.kind == VOLTAGE_BIPOLAR
    assert field.unit == "mV"


def test_register_scalar_stores_values_as_is() -> None:
    # register_scalar no longer conditions — the importer does. A negative
    # activation field is stored verbatim (no accidental sign flip).
    epmap = EPMap(map_name="m", study_name="s")
    epmap.register_scalar("primary", np.array([-30.0, -10.0, -5.0]), kind=ACTIVATION_TIME)
    np.testing.assert_array_equal(epmap.get_scalar("primary"), np.array([-30.0, -10.0, -5.0]))


def test_pacemap_is_relative_comparison(ensite_like_map) -> None:
    epmap = EPMap(map_name="m", study_name="s")
    epmap.register_scalar("primary", np.array([90.0, 50.0]), kind=PACEMAP_SCORE)
    assert epmap.get_field("primary").relative_comparison is True
    # voltage is not a relative-comparison quantity
    assert ensite_like_map.get_field("voltage_bipolar").relative_comparison is False


def test_one_map_holds_multiple_kinds_at_once() -> None:
    """A single map may carry activation AND voltage AND pace-map together —
    they are independent named fields, not a mutually exclusive slot."""
    vertices, triangles = make_synthetic_atrium(resolution=16)
    n = vertices.shape[0]
    epmap = EPMap(
        map_name="multi",
        study_name="s",
        vertices=vertices,
        triangles=triangles,
        xyz=vertices.copy(),
    )
    epmap.register_scalar("activation_time", np.linspace(-40.0, 40.0, n), kind=ACTIVATION_TIME)
    epmap.register_scalar("voltage_bipolar", np.linspace(0.05, 3.0, n), kind=VOLTAGE_BIPOLAR)
    epmap.register_scalar("pacemap_score", np.linspace(0.0, 100.0, n), kind=PACEMAP_SCORE)

    # all three coexist and resolve independently, with their own semantics
    assert set(epmap.scalar_fields) == {"activation_time", "voltage_bipolar", "pacemap_score"}
    assert epmap.get_field("activation_time").unit == "ms"
    assert epmap.get_field("voltage_bipolar").unit == "mV"
    assert epmap.get_field("pacemap_score").relative_comparison is True

    # each is independently analysable on the same mesh
    for name in ("activation_time", "voltage_bipolar", "pacemap_score"):
        areas = epmap.calculate_areas_for_intervals([(0.0, 1e6)], scalar_name=name, distance=1000.0)
        assert len(areas) == 1 and np.isfinite(areas[0])


def test_register_scalar_unipolar_roundtrip(carto_like_map) -> None:
    field = np.arange(carto_like_map.vertices.shape[0], dtype=float)
    carto_like_map.register_scalar("uni", field, kind=VOLTAGE_UNIPOLAR)
    np.testing.assert_array_equal(carto_like_map.get_scalar("uni"), field)


# --- analysis methods accept a vendor-neutral scalar name -----------------


def test_calculate_areas_carto_act_path(carto_like_map) -> None:
    areas = carto_like_map.calculate_areas_for_intervals(
        [(0.0, 50.0), (50.0, 100.0)], scalar_name="act", distance=1000.0
    )
    assert len(areas) == 2
    assert all(np.isfinite(a) for a in areas)


def test_calculate_areas_ensite_voltage_path(ensite_like_map) -> None:
    # Would have raised "Unsupported scalar_name" before the refactor.
    areas = ensite_like_map.calculate_areas_for_intervals(
        [(0.0, 1.0), (1.0, 10.0)], scalar_name="voltage_bipolar", distance=1000.0
    )
    assert len(areas) == 2
    assert all(np.isfinite(a) for a in areas)


# --- the analysis default is the map's own primary quantity ----------------


def test_primary_scalar_prefers_the_most_representative_quantity() -> None:
    from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR

    m = EPMap(map_name="m", study_name="s")
    m.register_scalar("voltage_bipolar", np.array([1.0]), kind=VOLTAGE_BIPOLAR)
    assert m.primary_scalar() == "voltage_bipolar"

    m.register_scalar("activation_time", np.array([2.0]), kind=ACTIVATION_TIME)
    assert m.primary_scalar() == "activation_time"  # outranks voltage


def test_primary_scalar_falls_back_to_whatever_exists() -> None:
    m = EPMap(map_name="m", study_name="s")
    m.register_scalar("Peak Neg", np.array([1.0]), kind="unknown")
    assert m.primary_scalar() == "Peak Neg"


def test_primary_scalar_is_none_without_fields() -> None:
    assert EPMap(map_name="m", study_name="s").primary_scalar() is None


def test_carto_and_ensite_answer_to_the_same_name() -> None:
    """A cross-vendor query — the thing the old act/vol naming made impossible."""
    from pulse_ep.core.importers.carto import register_carto_scalars
    from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR

    carto = EPMap(map_name="c", study_name="s")
    register_carto_scalars(carto, np.array([[10.0, 1.5], [20.0, 2.5]]))

    ensite = EPMap(map_name="e", study_name="s")
    ensite.register_scalar("voltage_bipolar", np.array([0.5, 0.9]), kind=VOLTAGE_BIPOLAR)

    for m in (carto, ensite):
        assert m.get_scalar("voltage_bipolar") is not None
        assert m.field_of_kind(VOLTAGE_BIPOLAR).kind == VOLTAGE_BIPOLAR


# --- rendering a map that has no legacy xyz array --------------------------


def test_measurement_positions_fall_back_to_measurement_points() -> None:
    """EnSite X maps never populate the legacy CARTO ``xyz`` array, so anything
    reading it directly rejected every one of them."""
    from pulse_ep.core.measurement import MeasurementPoint

    m = EPMap(map_name="m", study_name="s")
    assert m.measurement_positions() is None

    m.measurement_points = [
        MeasurementPoint(position=np.array([1.0, 2.0, 3.0])),
        MeasurementPoint(position=np.array([4.0, 5.0, 6.0])),
    ]
    np.testing.assert_allclose(m.measurement_positions(), [[1, 2, 3], [4, 5, 6]])

    m.xyz = np.array([[9.0, 9.0, 9.0]])
    np.testing.assert_allclose(m.measurement_positions(), [[9, 9, 9]])  # legacy wins


def test_a_map_without_measurements_still_renders() -> None:
    """A DIF mesh carrying only per-vertex fields has nothing to mask against;
    its values must pass through rather than the whole map failing to render."""
    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    epmap = EPMap(map_name="geometry-only", study_name="s", vertices=vertices, triangles=triangles)
    epmap.register_scalar("voltage_bipolar", 0.05 + scores / 100.0, kind=VOLTAGE_BIPOLAR)

    assert epmap.measurement_positions() is None  # no xyz, no measurement points
    mesh, values = epmap.interpolate_scalar_values(
        epmap.get_scalar("voltage_bipolar"),
        scalar_name="voltage_bipolar",
        distance_threshold=5.0,
    )
    assert mesh.n_points == len(values)
    assert np.isfinite(values).all()
