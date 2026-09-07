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
    ACTIVATION_TIME,
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


def test_pace_scores_use_negative_activation_values_with_explicit_metadata():
    epmap = _map(voltage_bipolar=[0.1, 0.2, 0.3, 0.4])
    scores = np.array([90.0, -80, 0, np.nan])
    epmap.register_scalar(PACEMAP_SCORE, scores.copy(), kind=PACEMAP_SCORE)
    u = to_userdata(epmap)
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 0], [-90, -80, 0, np.nan])
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 1], [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(epmap.get_scalar(PACEMAP_SCORE), scores)
    assert u["pulse_ep"]["surface_activation_kind"] == PACEMAP_SCORE
    assert u["pulse_ep"]["surface_activation_encoding"] == "negative_score"
    assert u["pulse_ep"]["surface_activation_unit"] == "%"
    assert any("negative score (%)" in n for n in u["notes"])
    assert not any("not representable" in n and PACEMAP_SCORE in n for n in u["notes"])


def test_a_missing_quantity_is_a_gap_with_a_reason():
    u = to_userdata(_map(voltage_bipolar=[1, 2, 3, 4]))
    assert np.isnan(u["surface"]["act_bip"][:, 0]).all()
    assert any("no activation_time" in n for n in u["notes"])
    assert any("no voltage_unipolar" in n for n in u["notes"])


def test_pace_point_annotations_encode_scores_and_leave_unscored_beats_missing():
    epmap = _map(pacemap_score=[90, 80, 70, 60])
    scored = MeasurementPoint(
        position=np.array([0.5, 0.5, 0]),
        annotations={"reference": 1250, "map": 1160, "woi_from": -200, "woi_to": 50},
    )
    scored.add("pacemap_score", 90, PACEMAP_SCORE)
    # A reference beat may have no derived score; surface semantics must
    # still prevent its sentinel from masquerading as a valid score.
    reference = MeasurementPoint(
        position=np.array([0.5, 0.5, 0]), annotations={"reference": 1250, "map": -8750}
    )
    epmap.measurement_points = [scored, reference]
    u = to_userdata(epmap)
    annotations = u["electric"]["annotations"]
    np.testing.assert_allclose(
        annotations["mapAnnot"] - annotations["referenceAnnot"], [-90, np.nan]
    )
    np.testing.assert_array_equal(annotations["referenceAnnot"], [1250, 1250])
    np.testing.assert_array_equal(annotations["woi"][0], [-200, 50])
    assert scored.annotations["map"] == 1160  # source data is unchanged
    assert any("2 pace-mapping points" in note for note in u["notes"])


def test_point_semantics_control_annotations_on_a_mixed_map():
    from pulse_ep.core.scalar_field import ACTIVATION_TIME

    epmap = _map(activation_time=[1, 2, 3, 4], pacemap_score=[90, 80, 70, 60])
    points = []
    for kind, value in ((PACEMAP_SCORE, 90), (ACTIVATION_TIME, -90)):
        point = MeasurementPoint(
            position=np.array([0.5, 0.5, 0]), annotations={"reference": 1250, "map": 1160}
        )
        point.add(kind, value, kind)
        points.append(point)
    epmap.measurement_points = points
    annotations = to_userdata(epmap)["electric"]["annotations"]
    assert annotations["mapAnnot"][0] - annotations["referenceAnnot"][0] == -90
    assert annotations["mapAnnot"][1] - annotations["referenceAnnot"][1] == -90


def test_real_lat_keeps_precedence_and_sign_on_a_mixed_surface():
    epmap = _map(activation_time=[-10, 0, 10, 20], pacemap_score=[90, 80, 70, 60])
    u = to_userdata(epmap)
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 0], [-10, 0, 10, 20])
    assert u["pulse_ep"]["surface_activation_kind"] == "activation_time"
    assert u["pulse_ep"]["surface_activation_encoding"] == "identity"
    assert u["pulse_ep"]["surface_activation_unit"] == "ms"


def test_a_point_score_without_raw_annotations_gets_a_declared_encoding_origin():
    epmap = _map(pacemap_score=[90, 80, 70, 60])
    point = MeasurementPoint(position=np.array([0.5, 0.5, 0]))
    point.add(PACEMAP_SCORE, 87.5, PACEMAP_SCORE)
    epmap.measurement_points = [point]
    u = to_userdata(epmap)
    annotations = u["electric"]["annotations"]
    np.testing.assert_allclose(annotations["referenceAnnot"], [0])
    np.testing.assert_allclose(annotations["mapAnnot"], [-87.5])
    assert np.isnan(annotations["woi"]).all()
    assert u["pulse_ep"]["point_activation_kinds"] == [PACEMAP_SCORE]
    assert any("zero reference solely to encode the score" in n for n in u["notes"])
    assert point.annotations == {}


def test_additional_quantities_are_available_as_openep_signal_maps():
    epmap = _map(voltage_bipolar=[1, 2, 3, 4])
    epmap.register_scalar("cfe_mean", np.array([5.0, 6, 7, 8]), kind="cfe_mean")
    u = to_userdata(epmap)
    assert any("signalMaps" in n and "cfe_mean" in n for n in u["notes"])
    fields = {f["name"]: f for f in u["surface"]["signalMaps"]}
    np.testing.assert_array_equal(fields["cfe_mean"]["map"], [5, 6, 7, 8])
    assert fields["cfe_mean"]["unit"] == "ms"


def test_named_fields_keep_duplicate_kinds_original_scores_and_validity():
    epmap = _map(pacemap_score=[90, 80, 70, 60])
    epmap.register_scalar(
        "micro custom",
        np.array([0.1, np.nan, 0.3, 0.4]),
        kind=VOLTAGE_BIPOLAR,
        unit="mV",
        source="vendor:channel",
        status_mask=np.array([True, False, True, False]),
    )
    epmap.register_scalar("second_bipole", np.array([1, 2, 3, 4]), kind=VOLTAGE_BIPOLAR)
    u = to_userdata(epmap)
    fields = {f["name"]: f for f in u["surface"]["signalMaps"]}
    assert set(fields) == set(epmap.scalar_fields)
    np.testing.assert_array_equal(fields["pacemap_score"]["map"], [90, 80, 70, 60])
    np.testing.assert_array_equal(u["surface"]["act_bip"][:, 0], [-90, -80, -70, -60])
    np.testing.assert_allclose(fields["micro custom"]["map"], [0.1, np.nan, 0.3, 0.4])
    assert fields["micro custom"]["source"] == "vendor:channel"
    np.testing.assert_array_equal(fields["micro custom"]["statusMask"], [True, False, True, False])
    np.testing.assert_array_equal(fields["second_bipole"]["map"], [1, 2, 3, 4])


def test_signal_properties_align_sparse_values_and_keep_different_units_apart():
    points = [MeasurementPoint(position=np.array([i, 0, 0])) for i in range(3)]
    points[0].add("cfe", 12.0, "cfe_mean", "ms")
    points[1].add("cfe", 0.02, "cfe_mean", "s")
    points[2].add("other", 3.0, "unknown", "count")
    epmap = _map()
    epmap.measurement_points = points
    props = to_userdata(epmap)["electric"]["signalProps"]
    assert len(props) == 3
    by_key = {(f["fieldName"], f["unit"]): f for f in props}
    np.testing.assert_allclose(by_key["cfe", "ms"]["value"], [12, np.nan, np.nan])
    np.testing.assert_allclose(by_key["cfe", "s"]["value"], [np.nan, 0.02, np.nan])
    assert by_key["cfe", "ms"]["name"] == ["cfe", "", ""]
    assert by_key["other", "count"]["propSettings"] == ""


def test_standard_slots_convert_declared_units_and_preserve_named_originals():
    m = _map()
    m.register_scalar(
        "lat_seconds", np.array([0.01, 0.02, 0.03, 0.04]), kind=ACTIVATION_TIME, unit="s"
    )
    m.register_scalar(
        "volts",
        np.array([0.001, 0.002, 0.003, 0.004]),
        kind=VOLTAGE_BIPOLAR,
        unit="V",
        status_mask=np.array([True, False, True, True]),
    )
    p = MeasurementPoint(position=np.zeros(3), annotations={"annotation_unit": "ms"})
    p.add("lat_seconds", 0.01, ACTIVATION_TIME, "s")
    p.add("microvolts", 2000, VOLTAGE_BIPOLAR, "uV")
    m.measurement_points = [p]
    u = to_userdata(m)
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 0], [10, 20, 30, 40])
    np.testing.assert_allclose(u["surface"]["act_bip"][:, 1], [1, np.nan, 3, 4])
    assert u["electric"]["voltages"]["bipolar"][0] == 2
    assert u["pulse_ep"]["lat_ms"][0] == 10
    assert u["electric"]["annotations"]["mapAnnot"][0] == 10
    fields = {f["name"]: f for f in u["surface"]["signalMaps"]}
    assert fields["lat_seconds"]["unit"] == "s"
    np.testing.assert_allclose(fields["volts"]["map"], [0.001, 0.002, 0.003, 0.004])


def test_unsupported_standard_units_are_not_mislabelled():
    m = _map()
    m.register_scalar("unknown_voltage", np.ones(4), kind=VOLTAGE_BIPOLAR, unit="counts")
    p = MeasurementPoint(position=np.zeros(3))
    p.add("unknown_voltage", 20, VOLTAGE_BIPOLAR, "counts")
    m.measurement_points = [p]
    u = to_userdata(m)
    assert np.isnan(u["surface"]["act_bip"][:, 1]).all()
    assert np.isnan(u["electric"]["voltages"]["bipolar"]).all()
    assert any("unit" in note and "counts" in note for note in u["notes"])


def test_empty_properties_and_geometry_metadata_are_explicit():
    u = to_userdata(_map(), system_name="ensite")
    assert u["systemName"] == "ensitex"
    assert u["surface"]["signalMaps"] == []
    assert u["electric"]["signalProps"] == []
    np.testing.assert_array_equal(u["surface"]["normals"], np.tile([0, 0, 1], (4, 1)))


def test_malformed_named_fields_are_reported_instead_of_misaligned():
    epmap = _map(cfe_mean=[1, 2])
    u = to_userdata(epmap)
    assert u["surface"]["signalMaps"] == []
    assert any("2 values for 4 vertices" in note for note in u["notes"])


def test_extensible_fields_survive_mat_export(tmp_path):
    from scipy.io import loadmat

    epmap = _map(cfe_mean=[1, np.nan, 3, 4])
    point = MeasurementPoint(position=np.array([0, 0, 0]))
    point.add("fractionation", 2.5, "fractionation")
    epmap.measurement_points = [point]
    path = tmp_path / "extended.mat"
    write_userdata(epmap, path, system_name="ensite")
    u = loadmat(path, simplify_cells=True)["userdata"]
    assert u["systemName"] == "ensitex"
    np.testing.assert_allclose(u["surface"]["signalMaps"]["map"], [1, np.nan, 3, 4])
    assert u["electric"]["signalProps"]["value"] == 2.5


def test_mat_point_names_and_tags_have_one_cell_per_point(tmp_path):
    from scipy.io import loadmat

    epmap = _map()
    epmap.measurement_points = [
        MeasurementPoint(position=np.array([0, 0, 0]), source_id="point-123", tags=[]),
        MeasurementPoint(position=np.array([1, 0, 0]), source_id="point-456", tags=["Scar", "Tag"]),
    ]
    path = tmp_path / "points.mat"
    write_userdata(epmap, path)
    userdata = loadmat(path, struct_as_record=False)["userdata"][0, 0]
    electric = userdata.electric[0, 0]
    # Native MATLAB triangulation rejects integer connectivity matrices.
    assert userdata.surface[0, 0].triRep[0, 0].Triangulation.dtype == np.float64
    assert electric.names.shape == electric.tags.shape == (2, 1)
    assert electric.voltages[0, 0].bipolar.shape == (2, 1)
    assert electric.names[0, 0].item() == "point-123"


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
    # OpenEP force courses use milliseconds relative to the point's origin.
    np.testing.assert_allclose(e["force"]["time_force"][0][:, 0], [-20, 0, 20])


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
    assert any("matched per-segment recording" in n for n in notes)


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
