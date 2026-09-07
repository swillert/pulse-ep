"""Signal identity, timing, missing data and calibration across OpenEP exports."""

import numpy as np
import pytest

from pulse_ep import EPMap
from pulse_ep.core.importers.carto_signal import parse_carto_force
from pulse_ep.core.importers.ensite_signal import iter_dxl_waveforms
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.openep import to_userdata
from pulse_ep.core.placed_point import ABLATION, ABLATION_PFA, PlacedPoint
from pulse_ep.core.waveform import Waveform


def carto_wave(point_id="7", rate=1000, unit="mV"):
    # Channels deliberately differ from the order in the point's metadata.
    return Waveform(
        data=np.arange(20, dtype=float).reshape(4, 5),
        channels=["V1", "20A_2", "CS1-CS2", "20A_1-2", "20A_1"],
        units=[unit] * 5,
        sample_rate=rate,
        signal_type="ecg",
        meta={
            "start_time": 123,
            "map_name": "test",
            "points": [
                {
                    "point_id": point_id,
                    "mapping_channels": {
                        "bipolar": "20A_1-2",
                        "unipolar": "20A_1",
                        "reference": "CS1-CS2",
                    },
                }
            ],
        },
    )


def map_with_points():
    m = EPMap(map_name="test", study_name="test")
    p = MeasurementPoint(
        position=np.zeros(3),
        source_id="7",
        annotations={"reference": 2, "map": 3, "woi_from": -1, "woi_to": 1},
        electrodes={"20A_1": np.array([1, 2, 3]), "20A_2": np.array([4, 5, 6])},
    )
    p.add("activation_time", 1, "activation_time")
    m.measurement_points = [p, MeasurementPoint(position=np.ones(3), source_id="8")]
    return m


def test_carto_channels_match_by_identity_and_preserve_missing_points():
    w = carto_wave()
    u = to_userdata(map_with_points(), signal_windows=[w])
    e = u["electric"]
    np.testing.assert_array_equal(e["egm"][0], w.data[:, 3])
    np.testing.assert_array_equal(e["egmUni"][0, :, 0], w.data[:, 4])
    np.testing.assert_array_equal(e["egmUni"][0, :, 1], w.data[:, 1])
    np.testing.assert_array_equal(e["egmRef"][0], w.data[:, 2])
    np.testing.assert_array_equal(e["ecg"][0, :, 0], w.data[:, 0])
    np.testing.assert_array_equal(e["egmUniX"][0, :, 1], [4, 5, 6])
    assert np.isnan(e["egm"][1]).all()
    assert e["ecgNames"] == ["V1"] and e["sampleFrequency"] == 1000
    assert u["pulse_ep"]["signals"]["points_with_bipolar"] == 1


def test_ambiguous_or_other_map_windows_are_not_assigned():
    w = carto_wave()
    w.meta["map_name"] = "other"
    assert "egm" not in to_userdata(map_with_points(), signal_windows=[w])["electric"]
    u = to_userdata(map_with_points(), signal_windows=[carto_wave(), carto_wave()])
    assert "egm" not in u["electric"]
    assert any("ambiguous" in n for n in u["notes"])


def test_mixed_sampling_rates_require_explicit_resolution():
    with pytest.raises(ValueError, match="mixed signal sampling rates"):
        to_userdata(map_with_points(), signal_windows=[carto_wave(), carto_wave("8", 2000)])


def test_unknown_amplitudes_remain_unknown_until_explicit_calibration():
    m, w = map_with_points(), carto_wave(unit="unknown")
    raw = to_userdata(m, signal_windows=[w])
    calibrated = to_userdata(m, signal_windows=[w], signal_scale_to_mv=0.25)
    assert raw["pulse_ep"]["signals"]["units"]["bipolar"][0] == "unknown"
    assert calibrated["pulse_ep"]["signals"]["units"]["bipolar"][0] == "mV"
    np.testing.assert_allclose(calibrated["electric"]["egm"], raw["electric"]["egm"] * 0.25)
    with pytest.raises(ValueError, match="positive"):
        to_userdata(m, signal_windows=[w], signal_scale_to_mv=-1)


DXL = """Export Data Element: DxL
Sample rate:,2000
Waveform samples exported:,4
Trace,Freeze Grp #,(Point #),startTime (abs),rovTime (wave samples),0,1,2,3
M1-M2,4,7,1000,2,0.1,0.2,0.3,0.4
EOF
"""


def test_dxl_signals_use_reference_group_and_zero_based_ticks():
    _, bip, _ = next(iter_dxl_waveforms(DXL, "map/Wave_rov.csv"))
    _, ref, pid = next(iter_dxl_waveforms(DXL.replace("M1-M2", "CS"), "map/Wave_refs.csv"))
    assert pid is None
    m = map_with_points()
    point = m.measurement_points[0]
    point.measurements["activation_time"].value = 0.5
    point.annotations = {
        "source_folder": "map",
        "freeze_group": "4",
        "annotation_unit": "ms",
        "reference_sample_zero_based": 1,
        "woi_from": -0.5,
        "woi_to": 0.5,
    }
    u = to_userdata(m, signal_windows=[bip, ref], system_name="ensite")
    a = u["electric"]["annotations"]
    assert a["referenceAnnot"][0] == 2
    assert a["mapAnnot"][0] == 3
    np.testing.assert_allclose(a["woi"][0], [-1, 1])
    np.testing.assert_allclose(u["electric"]["egmRef"][0], [0.1, 0.2, 0.3, 0.4])
    assert u["electric"]["sampleFrequency"] == 2000
    # A different acquisition group must not receive this reference.
    point.annotations["freeze_group"] = "5"
    e = to_userdata(m, signal_windows=[bip, ref])["electric"]
    assert np.isnan(e["egmRef"]).all()


def test_dxl_truncated_samples_fail_but_explicitly_absent_reference_is_empty():
    with pytest.raises(ValueError, match="truncated"):
        list(iter_dxl_waveforms(DXL.replace(",0.4", ""), "Wave_rov.csv"))
    assert (
        list(iter_dxl_waveforms(DXL.replace("exported:,4", "exported:,0"), "Wave_refs2.csv")) == []
    )


def test_rf_selection_keeps_pfa_and_different_indices_out_of_rf_slots():
    points = [
        PlacedPoint(
            type=ABLATION,
            position=np.array([1, 2, 3]),
            attributes={"average_force_g": 12, "duration_s": 20, "power": 30},
        ),
        PlacedPoint(type=ABLATION_PFA, position=np.array([4, 5, 6])),
    ]
    u = to_userdata(map_with_points(), ablation_points=points)
    assert u["rfindex"]["tag"]["X"].shape == (1, 3)
    assert u["rfindex"]["tag"]["avgForce"][0] == 12
    assert u["rfindex"]["tag"]["time"][0] == 20
    assert np.isnan(u["rfindex"]["tag"]["maxPower"][0])
    assert u["pulse_ep"]["ablation"]["attributes"][0]["power"] == 30


def test_carto_force_uses_point_id_and_instantaneous_value_not_nearest_study_time():
    text = """ContactForce.txt_2.0
IntervalNonGraph=1000
123000 15 30 40 0
Index\tTime\tTimestamp\tForceValue\tAxialAngle\tLateralAngle
1 -50 122950 9 20 30
2 0 123000 10 21 31
3 50 123050 11 22 32
"""
    w = parse_carto_force(text)
    w.meta["point_id"] = "7"
    u = to_userdata(map_with_points(), force_windows=[w])
    force = u["electric"]["force"]
    assert force["force"][0] == 15
    assert np.isnan(force["force"][1])
    assert force["time_force"].shape == (2, 3, 2)
    np.testing.assert_array_equal(force["time_force"][0, :, 0], [-50, 0, 50])


def test_ecg_from_a_different_window_start_is_not_aligned_by_length_alone():
    bip, ref = carto_wave(), carto_wave()
    bip.channels[0] = "not-an-ECG"
    bip.meta["points"][0]["mapping_channels"] = {"bipolar": "20A_1-2"}
    ref.meta["points"][0]["mapping_channels"] = {"reference": "CS1-CS2"}
    ref.meta["start_time"] += 1
    u = to_userdata(map_with_points(), signal_windows=[bip, ref])
    assert np.isnan(u["electric"]["egmRef"]).all()
    assert np.isnan(u["electric"]["ecg"]).all()


def test_each_dxl_ecg_lead_is_bound_independently():
    m = map_with_points()
    m.measurement_points[0].annotations["source_folder"] = "map"
    waves = [
        next(iter_dxl_waveforms(DXL.replace("M1-M2", lead), "map/Wave_ecg.csv"))[1]
        for lead in ("V1", "V2")
    ]
    u = to_userdata(m, signal_windows=waves)
    assert u["electric"]["ecgNames"] == ["V1", "V2"]
    np.testing.assert_allclose(u["electric"]["ecg"][0, :, 0], [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(u["electric"]["ecg"][0, :, 1], [0.1, 0.2, 0.3, 0.4])
    assert np.isnan(u["electric"]["egm"]).all()


def test_second_unipole_is_retained_when_other_roles_are_absent():
    m = map_with_points()
    m.measurement_points[0].annotations["source_folder"] = "map"
    wave = next(iter_dxl_waveforms(DXL, "map/Wave_uni_proximal.csv"))[1]
    u = to_userdata(m, signal_windows=[wave])
    np.testing.assert_allclose(u["electric"]["egmUni"][0, :, 1], [0.1, 0.2, 0.3, 0.4])


def test_contact_force_must_belong_to_the_selected_map():
    wave = Waveform(
        data=np.array([[12.0], [15.0]]),
        channels=["ForceValue"],
        units=["g"],
        sample_rate=20,
        time=np.array([0, 50]),
        signal_type="contact_force",
        meta={"format": "carto_force", "point_id": "7", "map_name": "another map"},
    )
    u = to_userdata(map_with_points(), force_windows=[wave])
    assert np.isnan(u["electric"]["force"]["force"]).all()


@pytest.mark.parametrize("factor", [-1, 0, float("nan"), float("inf")])
def test_calibration_validation_also_applies_without_available_signals(factor):
    with pytest.raises(ValueError, match="finite and positive"):
        to_userdata(map_with_points(), signal_windows=[], signal_scale_to_mv=factor)
