"""Where a point's beat sits in the signal recorded for it.

``measurements`` carries the *derived* value — the activation time, or the
pace-match score. The components it was derived from (the window's start, the
reference and mapping annotations, the window of interest) survived only in
CARTO's fixed-column ``ep_map_points``, which the queue import path never
writes and no EnSiteX study has at all. Since signal windows are imported,
those components are what tells a reader where in 2500 samples to look.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.carto import (
    carto_points_to_measurements,
    point_annotations,
)
from pulse_ep.core.importers.carto_signal import parse_point_export
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.models import measurement_points_to_models

_EXPORT = {
    "point_index": 0,
    "carto_point_id": 1,
    "position_x": 1.0,
    "position_y": 2.0,
    "position_z": 3.0,
    "start_time": 13500280,
    "reference_annotation": 2000.0,
    "map_annotation": 1904.0,
    "woi_from": -170.0,
    "woi_to": 129.0,
    "unipolar_voltage": 2.4,
    "bipolar_voltage": 0.8,
}

_POINT_XML = """<Point ID="1">
    <Annotations StartTime="13500280" Reference_Annotation="2000" Map_Annotation="1904" />
    <WOI From="-170" To="129" />
    <ECG FileName="m_ECG_Export_13500280.txt" UnipolarMappingChannel="M1"
         BipolarMappingChannel="MCC_Abl_BiPolar_1" ReferenceChannel="CS1-CS2" />
</Point>
"""


def test_the_components_of_the_derived_value_are_kept():
    assert point_annotations(_EXPORT) == {
        "start_time": 13500280,
        "reference": 2000,
        "map": 1904,
        "woi_from": -170,
        "woi_to": 129,
    }


def test_what_the_export_does_not_carry_is_absent_not_null():
    """Absent means "not exported" — the same rule as for a measurement."""
    assert point_annotations({"start_time": 5}) == {"start_time": 5}
    assert point_annotations({}) == {}


def test_the_unscored_reference_beat_keeps_no_annotation():
    """CARTO's ``-10000`` is a no-datum marker, not an annotation at sample -10000."""
    annotations = point_annotations({**_EXPORT, "map_annotation": -10000.0})
    assert "map" not in annotations
    assert annotations["reference"] == 2000  # the rest of the point is untouched


def test_a_point_carries_them_beside_its_derived_value():
    # a positive difference, so the sign rule reads this as an activation map
    export = {**_EXPORT, "map_annotation": 2050.0}
    (point,) = carto_points_to_measurements([export])

    assert point.annotations["reference"] == 2000
    assert point.annotations["map"] == 2050
    # the derived value is still there under its own name, and the components
    # it came from are now beside it rather than only in the legacy table
    assert point.get("activation_time") == 50.0
    assert point.annotations["map"] - point.annotations["reference"] == 50.0


def test_they_survive_the_orm_in_both_directions():
    point = MeasurementPoint(
        position=np.array([0.0, 0.0, 0.0]),
        annotations={"start_time": 1, "reference": 2000, "map": 1904},
    )
    (row,) = measurement_points_to_models([point], map_id=3)
    assert row.annotations == {"start_time": 1, "reference": 2000, "map": 1904}
    assert row.to_measurement_point().annotations == row.annotations


def test_a_point_without_them_is_serialised_as_an_empty_map():
    point = MeasurementPoint(position=__import__("numpy").array([0.0, 0.0, 0.0]))
    (row,) = measurement_points_to_models([point], map_id=3)
    assert row.annotations == {}
    assert row.to_measurement_point().annotations == {}


def test_a_point_and_its_stored_window_describe_themselves_identically():
    """The reason for these key names: one vocabulary, two places.

    A stored waveform records the same facts, parsed from the same point XML.
    If the two disagreed, a client would have to know which one to believe.
    """
    from_signal = parse_point_export(_POINT_XML)["annotations"]
    from_point = point_annotations(_EXPORT)

    shared = set(from_point) & set(from_signal)
    assert shared == {"start_time", "reference", "map", "woi_from", "woi_to"}
    assert all(from_point[key] == from_signal[key] for key in shared)
