"""Packing a map into OpenEP's ``userdata`` structure.

The mapping lives in Python precisely so that it can be pinned here: the
MATLAB side only rebuilds the ``triangulation`` object a .mat cannot carry,
and no CI runs MATLAB.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.openep import to_userdata, write_userdata
from pulse_ep.core.scalar_field import (
    PACEMAP_SCORE,
    VOLTAGE_BIPOLAR,
    VOLTAGE_UNIPOLAR,
)

_VERTS = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
_TRIS = np.array([[0, 1, 2], [0, 2, 3]])


def _map(**fields) -> EPMap:
    epmap = EPMap(
        map_name="m",
        study_name="s",
        vertices=_VERTS,
        triangles=_TRIS,
        normals=np.tile([0.0, 0, 1], (4, 1)),
    )
    for kind, values in fields.items():
        epmap.register_scalar(kind, np.asarray(values, dtype=float), kind=kind)
    return epmap


def test_triangles_cross_the_index_boundary():
    """pulse-ep counts vertices from zero, MATLAB from one."""
    u = to_userdata(_map())
    tri = u["surface"]["triRep"]["Triangulation"]
    np.testing.assert_array_equal(tri, _TRIS + 1)
    assert tri.min() == 1
    np.testing.assert_allclose(u["surface"]["triRep"]["X"], _VERTS)


def test_quantities_land_in_the_slots_that_mean_them():
    u = to_userdata(_map(activation_time=[1, 2, 3, 4], voltage_bipolar=[0.1, 0.2, 0.3, 0.4]))
    act_bip = u["surface"]["act_bip"]
    assert act_bip.shape == (4, 2)
    np.testing.assert_allclose(act_bip[:, 0], [1, 2, 3, 4])
    np.testing.assert_allclose(act_bip[:, 1], [0.1, 0.2, 0.3, 0.4])


def test_a_pace_map_does_not_pretend_to_be_an_activation_map():
    """The decision the whole exporter turns on.

    CARTO stores an activation time and a pace-match score in one slot, and
    pulse-ep learned to tell them apart. Writing the score into act_bip(:,1)
    would tell OpenEP this is an activation map, and every isochrone and
    conduction-velocity function downstream would agree — silently, and
    wrongly. The slot stays NaN and the note says why.
    """
    epmap = _map(voltage_bipolar=[0.1, 0.2, 0.3, 0.4])
    epmap.register_scalar(PACEMAP_SCORE, np.array([90.0, 80, 70, 60]), kind=PACEMAP_SCORE)

    u = to_userdata(epmap)
    assert np.isnan(u["surface"]["act_bip"][:, 0]).all()
    # …and the voltage that *is* there is untouched.
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 1], [0.1, 0.2, 0.3, 0.4])
    assert any(PACEMAP_SCORE in n for n in u["notes"])


def test_a_missing_quantity_is_a_gap_with_a_reason():
    u = to_userdata(_map(voltage_bipolar=[1, 2, 3, 4]))
    assert np.isnan(u["surface"]["act_bip"][:, 0]).all()
    assert any("no activation_time" in n for n in u["notes"])
    assert any("no voltage_unipolar" in n for n in u["notes"])


def test_quantities_openep_has_no_room_for_are_named_not_dropped():
    """OpenEP's surface has four slots; a pulse-ep map may carry a dozen."""
    epmap = _map(voltage_bipolar=[1, 2, 3, 4])
    epmap.register_scalar("cfe_mean", np.array([5.0, 6, 7, 8]), kind="cfe_mean")
    notes = to_userdata(epmap)["notes"]
    assert any("not representable" in n and "cfe_mean" in n for n in notes)


def test_measurement_points_become_the_electric_structure():
    epmap = _map(voltage_bipolar=[1, 2, 3, 4])
    point = MeasurementPoint(
        position=np.array([0.4, 0.4, 0.0]),
        source_id="P7",
        tags=["Scar"],
        annotations={"reference": -120.0, "map": -45.0, "woi_from": -200.0, "woi_to": 50.0},
    )
    point.add("voltage_bipolar", 0.25, VOLTAGE_BIPOLAR)
    point.add("voltage_unipolar", 1.5, VOLTAGE_UNIPOLAR)
    point.electrodes["CS_1"] = np.array([0.4, 0.4, 0.1])
    epmap.measurement_points = [point]

    e = to_userdata(epmap)["electric"]
    assert e["names"] == ["P7"] and e["tags"] == [["Scar"]]
    np.testing.assert_allclose(e["egmX"], [[0.4, 0.4, 0.0]])
    np.testing.assert_allclose(e["voltages"]["bipolar"], [0.25])
    np.testing.assert_allclose(e["voltages"]["unipolar"], [1.5])
    np.testing.assert_allclose(e["annotations"]["referenceAnnot"], [-120.0])
    np.testing.assert_allclose(e["annotations"]["mapAnnot"], [-45.0])
    np.testing.assert_allclose(e["annotations"]["woi"], [[-200.0, 50.0]])
    assert e["electrodeNames_bip"] == [["CS_1"]]


def test_points_are_projected_onto_the_surface():
    """``egmSurfX`` and ``barDirection`` are computed, not stored."""
    epmap = _map()
    epmap.measurement_points = [MeasurementPoint(position=np.array([0.9, 0.1, 5.0]))]
    e = to_userdata(epmap)["electric"]
    np.testing.assert_allclose(e["egmSurfX"], [[1.0, 0.0, 0.0]])
    np.testing.assert_allclose(e["barDirection"], [[0.0, 0.0, 1.0]])


def test_a_map_with_no_points_still_yields_a_usable_structure():
    e = to_userdata(_map())["electric"]
    assert e["egmX"].shape == (0, 3)
    assert e["annotations"]["woi"].shape == (0, 2)
    assert e["names"] == []


def test_ablation_data_is_left_empty_rather_than_guessed():
    """VisiTag sites are imported onto the *study*; which map each belongs to
    is not something the exports say."""
    assert to_userdata(_map())["rf"] == {}


def test_the_mat_file_round_trips(tmp_path):
    scipy_io = pytest.importorskip("scipy.io")
    epmap = _map(activation_time=[1, 2, 3, 4], voltage_bipolar=[5, 6, 7, 8])
    path = tmp_path / "map.mat"
    notes = write_userdata(epmap, path, study_name="S1")
    assert notes and "pulse-ep" in notes[0]

    back = scipy_io.loadmat(str(path), squeeze_me=True, struct_as_record=False)
    surface = back["userdata"].surface
    np.testing.assert_array_equal(surface.triRep.Triangulation, _TRIS + 1)
    np.testing.assert_allclose(surface.act_bip[:, 0], [1, 2, 3, 4])


def test_the_structure_survives_json():
    """MATLAB reads it over REST, so every value has to be JSON-expressible.

    NaN is not, and an empty OpenEP slot is exactly what NaN means here — a
    quantity this map never measured. It goes over as ``null``, which says the
    same thing in a form every client can read.
    """
    import json

    from pulse_ep.server.app import _jsonable

    epmap = _map(voltage_bipolar=[1, 2, 3, 4])
    epmap.measurement_points = [MeasurementPoint(position=np.array([0.5, 0.5, 0.0]))]

    payload = _jsonable(to_userdata(epmap))
    text = json.dumps(payload)  # raises on NaN with allow_nan=False? no — check ourselves
    assert "NaN" not in text and "Infinity" not in text
    round_tripped = json.loads(text)

    assert round_tripped["surface"]["triRep"]["Triangulation"] == (_TRIS + 1).tolist()
    # The activation-time column is absent on this map, and says so as null.
    assert [row[0] for row in round_tripped["surface"]["act_bip"]] == [None] * 4
    assert [row[1] for row in round_tripped["surface"]["act_bip"]] == [1.0, 2.0, 3.0, 4.0]
    assert round_tripped["surface"]["isVertexAtRim"] == [False] * 4
    assert round_tripped["notes"]


def _force_window(start: float, seconds=(0.0, 0.02, 0.04)):
    """A contact-force window as the EnSite X reader produces one."""
    from pulse_ep.core.waveform import Waveform

    n = len(seconds)
    return Waveform(
        data=np.column_stack(
            [np.linspace(10, 12, n), np.linspace(60, 62, n), np.linspace(20, 22, n)]
        ),
        channels=["totalForce_0", "alphaAngle_0", "thetaAngle_0"],
        units=["g", "deg", "deg"],
        signal_type="contact_force_computed",
        time=np.array(seconds),
        meta={"start_time": start},
    )


def _point_at(t: float) -> MeasurementPoint:
    return MeasurementPoint(position=np.array([0.5, 0.5, 0.0]), annotations={"start_time": t})


def test_force_is_found_for_a_point_the_window_covers():
    """OpenEP wants force per point; EnSite X records it per segment, so the
    absolute times are what tie the two together."""
    epmap = _map()
    epmap.measurement_points = [_point_at(1000.02)]
    e = to_userdata(epmap, force_windows=[_force_window(1000.0)])["electric"]

    assert e["force"]["force"][0] == pytest.approx(11.0)
    assert e["force"]["axialAngle"][0] == pytest.approx(61.0)
    assert e["force"]["lateralAngle"][0] == pytest.approx(21.0)
    # The course comes back on the study clock, not relative to the window.
    np.testing.assert_allclose(e["force"]["time_force"][0][:, 0], [1000.0, 1000.02, 1000.04])


def test_a_point_no_window_covers_is_nan_and_counted():
    """Not a failure mode to hide: a real export holds a force window from 92 s
    after its last mapping point."""
    epmap = _map()
    epmap.measurement_points = [_point_at(1000.02), _point_at(5000.0)]
    u = to_userdata(epmap, force_windows=[_force_window(1000.0)])

    force = u["electric"]["force"]
    assert force["force"][0] == pytest.approx(11.0)
    assert np.isnan(force["force"][1])
    assert any("1 of 2 points are not covered" in n for n in u["notes"])


def test_the_derived_course_is_declared_as_derived():
    epmap = _map()
    epmap.measurement_points = [_point_at(1000.02)]
    notes = to_userdata(epmap, force_windows=[_force_window(1000.0)])["notes"]
    assert any("slice of a per-segment window" in n for n in notes)


def test_without_windows_the_slots_exist_but_are_empty():
    """A caller that supplies none still gets the structure OpenEP expects."""
    epmap = _map()
    epmap.measurement_points = [_point_at(1000.0)]
    u = to_userdata(epmap)
    assert np.isnan(u["electric"]["force"]["force"]).all()
    assert any("no contact-force windows supplied" in n for n in u["notes"])


def test_a_carto_force_file_would_map_by_its_own_column_names():
    """The mapping is by quantity, not by spelling: CARTO calls the same three
    ForceValue, AxialAngle and LateralAngle."""
    from pulse_ep.core.openep import _force_channel

    window = _force_window(0.0)
    window.channels = ["ForceValue", "AxialAngle", "LateralAngle"]
    assert _force_channel(window, "force") == 0
    assert _force_channel(window, "axialAngle") == 1
    assert _force_channel(window, "lateralAngle") == 2
