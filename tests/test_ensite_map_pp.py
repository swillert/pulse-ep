"""Native structured Map_PP_*.csv parser (DxL point-parameter export)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_map_pp

_HDR = (
    "Rov trace,Electrodes,Channels,Freeze Grp #,(Point #),Ref trace, Ref2 trace,"
    "roving x,roving y,roving z,surface x,surface y,surface z,normal x,normal y,normal z,"
    "displayed,utilized,gold-starred,P-P,P-P valid,refTime (abs),adjTime (ms),"
    "left curtain (ms),right curtain (ms),force (g),actSeq, annot"
)
_MAP_PP = (
    "Export Data Element: DxL\n"
    "Map name:,Test Map\n"
    "Map type:,PP_bi\n"
    "# mapping pts:,2\n"
    "Data starts in row,6\n"
    f"{_HDR}\n"
    "HDGX A1-A2,A1 A2,99 100,1,37,..,..,49.8,-208.3,391.6,42.0,-215.2,392.0,"
    "-0.7,-0.7,0.0,1,0,0,0.965,1,1781787673.5,8,20,319,3.2,10000,\n"
    "HDGX A1-B1,A1 B1,99 103,1,38,..,..,49.8,-208.3,391.6,43.0,-216.2,393.0,"
    "-0.7,-0.7,0.0,1,0,0,0.500,0,1781787673.5,12,20,319,invalid,10000,\n"
)


def test_skips_preamble_and_reads_points():
    pts = parse_ensite_map_pp(_MAP_PP)
    assert len(pts) == 2
    p0 = pts[0]
    np.testing.assert_allclose(p0.position, [42.0, -215.2, 392.0])
    assert p0.source_id == "37"


def test_maps_columns_to_measurements():
    p0 = parse_ensite_map_pp(_MAP_PP)[0]
    assert p0.get("voltage_bipolar") == 0.965  # from P-P, map type PP_bi
    assert p0.get("activation_time") == 8.0  # adjTime (ms)
    assert p0.get("contact_force") == 3.2  # force (g)
    np.testing.assert_allclose(p0.electrodes["A1 A2"], [49.8, -208.3, 391.6])


def test_invalid_pp_and_force_are_dropped():
    p1 = parse_ensite_map_pp(_MAP_PP)[1]
    assert "voltage_bipolar" not in p1.measurements  # P-P valid == 0
    assert "contact_force" not in p1.measurements  # force == "invalid"
    assert p1.get("activation_time") == 12.0
