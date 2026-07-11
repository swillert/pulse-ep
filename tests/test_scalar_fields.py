"""Vendor-neutral scalar-field layer on :class:`pulse_ep.EPMap`.

Proves the Phase-0 refactor:

1. The legacy CARTO ``act_bip`` bridge still resolves as before
   (``"act"`` → column 0 with sign-normalisation, ``"vol"`` → column 1).
2. A map carrying only registered ``scalar_fields`` (as an EnSiteX voltage
   mesh would) flows through the same analysis methods.
3. ``kind`` is declared at registration and conditioning (activation
   sign-flip, sentinel masking) happens once, at import.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep import EPMap
from pulse_ep.core.scalar_field import (
    ACTIVATION_TIME,
    PACEMAP_SCORE,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
)
from pulse_ep.examples.demo_synthetic import (
    gaussian_score_field,
    make_synthetic_atrium,
)


@pytest.fixture
def carto_like_map():
    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    voltage = scores / 100.0  # stand-in second column
    return EPMap(
        map_name="carto",
        study_name="s",
        vertices=vertices,
        triangles=triangles,
        xyz=vertices.copy(),  # measurements sit on the vertices
        act_bip=np.column_stack([scores, voltage]),
    )


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


# --- resolver: legacy CARTO bridge ---------------------------------------


def test_get_scalar_carto_bridge_positive_is_passthrough(carto_like_map) -> None:
    # Gaussian scores are positive → no sign flip → exact passthrough.
    np.testing.assert_array_equal(carto_like_map.get_scalar("act"), carto_like_map.act_bip[:, 0])
    np.testing.assert_array_equal(carto_like_map.get_scalar("vol"), carto_like_map.act_bip[:, 1])


def test_get_scalar_prefers_registered_field(ensite_like_map) -> None:
    np.testing.assert_array_equal(
        ensite_like_map.get_scalar("voltage_bipolar"),
        ensite_like_map.get_field("voltage_bipolar").values,
    )


def test_get_scalar_unknown_raises(ensite_like_map) -> None:
    with pytest.raises(ValueError, match="Unsupported scalar_name"):
        ensite_like_map.get_scalar("does_not_exist")


def test_registered_field_shadows_act_bip(carto_like_map) -> None:
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
