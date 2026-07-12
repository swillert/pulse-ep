"""EnSite placed-point parsers: AutoMark (ablation), Lesions/Labels (markers)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import (
    parse_ensite_automarks,
    parse_ensite_labels,
    parse_ensite_markers,
)
from pulse_ep.core.placed_point import ABLATION, LANDMARK, MARKER

_AUTOMARK = (
    "Export Data Element: AutoMark_Data\n"
    "RF Episode,Lesion ID,Date,Time,Seconds since 1/1/1970,Microseconds,"
    "NavX ABL-D X (mm),NavX ABL-D Y (mm),NavX ABL-D Z (mm),Ampere Power (W)\n"
    "1,5,d,t,0,0,10.0,20.0,30.0,25.5\n"
    "1,6,d,t,0,0,11.0,21.0,31.0,30.0\n"
    "\n"
    "RF Episode,Lesion ID,Date,Time,Seconds since 1/1/1970,Microseconds,ABL D EKG (mV)\n"
    "1,5,d,t,0,0,0.1\n"
)

_LESIONS = (
    "Export Data Element: Lesions\n"
    "Text,Type,Surface,x,y,z,xt,yt,zt,xw,yw,zw,Proj Distance,Display,Visible,R,G,B,Diameter,Timestamp,Annotation\n"
    "L1,3DE,[N/A],-17.2,-105.7,42.3,-17.2,-105.7,42.3,-17.2,-105.7,42.3,1.88,1,1,1,1,0,5.0,13:16:37,note\n"
)


def test_automarks_are_ablation_points():
    pts = parse_ensite_automarks(_AUTOMARK)
    # only the first (NavX/power) section, not the EKG section
    assert len(pts) == 2
    p0 = pts[0]
    assert p0.type == ABLATION
    np.testing.assert_allclose(p0.position, [10.0, 20.0, 30.0])
    assert p0.attributes["power"] == 25.5
    assert p0.source_id == "5"


def test_lesions_are_markers_with_attributes():
    (p,) = parse_ensite_markers(_LESIONS)
    assert p.type == MARKER
    np.testing.assert_allclose(p.position, [-17.2, -105.7, 42.3])
    assert p.label == "L1"
    assert p.attributes["marker_type"] == "3DE"
    assert p.attributes["diameter"] == 5.0
    assert p.attributes["color"] == [1, 1, 0]
    assert p.attributes["annotation"] == "note"


def test_labels_are_landmarks():
    (p,) = parse_ensite_labels(_LESIONS)  # same Text,Type,x,y,z layout
    assert p.type == LANDMARK


def test_empty_or_missing_section_yields_no_points():
    assert parse_ensite_automarks("Export Data Element: AutoMark_Data\n(no header)\n") == []
    assert parse_ensite_markers("nothing here") == []
