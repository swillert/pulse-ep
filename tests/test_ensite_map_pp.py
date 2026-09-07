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
    assert p0.get("contact_force") == 3.2  # force (g)
    np.testing.assert_allclose(p0.electrodes["A1 A2"], [49.8, -208.3, 391.6])


def test_adjtime_is_annotation_not_activation():
    """``adjTime`` is the annotation window offset — real exports hold one
    constant value for every point — so it must not pose as activation time."""
    p0 = parse_ensite_map_pp(_MAP_PP)[0]
    assert p0.get("annotation_time") == 8.0
    assert "activation_time" not in p0.measurements


def test_invalid_pp_and_force_are_dropped():
    p1 = parse_ensite_map_pp(_MAP_PP)[1]
    assert "voltage_bipolar" not in p1.measurements  # P-P valid == 0
    assert "contact_force" not in p1.measurements  # force == "invalid"
    assert p1.get("annotation_time") == 12.0


def _channel_csv(map_type: str, value_col: str, v0: str, v1: str) -> str:
    """The same export, re-emitted for another DxL channel: identical columns
    and point ids, only the value column pair changes."""
    hdr = _HDR.replace("P-P,P-P valid", f"{value_col},{value_col} valid")
    body = _MAP_PP.split("\n")[6:8]
    rows = [r.replace(",0.965,1,", f",{v0},1,").replace(",0.500,0,", f",{v1},1,") for r in body]
    return (
        "Export Data Element: DxL\nMap name:,Test Map\n"
        f"Map type:,{map_type}\n# mapping pts:,2\nData starts in row,6\n"
        f"{hdr}\n" + "\n".join(rows) + "\n"
    )


def test_lat_channel_is_activation_time():
    p0 = parse_ensite_map_pp(_channel_csv("LAT_bi", "LAT", "193.028", "12.5"))[0]
    assert p0.get("activation_time") == 193.028
    assert "voltage_bipolar" not in p0.measurements


def test_each_dxl_channel_maps_to_its_own_measurement():
    for map_type, column, field in [
        ("Score_bi", "Score", "map_score"),
        ("CFEmean_bi", "CFE mean", "cfe_mean"),
        ("CFEstdDev_bi", "CFE StdDev", "cfe_stddev"),
        ("Fractionation_bi", "Fractionation (CFE count)", "fractionation"),
        ("PFreq_bi", "PeakFrequency", "peak_frequency"),
        ("PNeg_bi", "Peak Neg", "voltage_peak_negative"),
    ]:
        p0 = parse_ensite_map_pp(_channel_csv(map_type, column, "42.0", "1.0"))[0]
        assert p0.get(field) == 42.0, f"{map_type} -> {field}"


def test_unknown_channel_keeps_its_vendor_name():
    """A channel the lexicon does not know is still imported — under the
    export's own column name, so it stays visible instead of being dropped or
    silently mislabelled as a voltage."""
    p0 = parse_ensite_map_pp(_channel_csv("Whatever_bi", "Whatever", "7.5", "1.0"))[0]
    assert p0.get("Whatever") == 7.5
    assert p0.measurements["Whatever"].kind == "unknown"
    assert "voltage_bipolar" not in p0.measurements


def _cfe_export(polarity: str, value: float) -> str:
    """A CFEmean DxL export — same point set, only the polarity differs."""
    header = _HDR.replace("P-P,P-P valid", "CFEmean,CFEmean valid")
    row = (
        "HDGX A1-A2,A1 A2,99 100,1,37,..,..,49.8,-208.3,391.6,42.0,-215.2,392.0,"
        f"-0.7,-0.7,0.0,1,0,0,{value},1,1781787673.5,8,20,319,3.2,10000,\n"
    )
    return (
        "Export Data Element: DxL\n"
        "Map name:,Test Map\n"
        f"Map type:,CFEmean_{polarity}\n"
        "# mapping pts:,1\n"
        "Data starts in row,6\n"
        f"{header}\n" + row
    )


def test_a_unipolar_channel_does_not_overwrite_its_bipolar_namesake():
    """Both are ``cfe_mean``; only ``PP`` carries polarity in its *kind*.

    A map's channels merge by point id, so one name for both meant the file
    parsed last won and the other measurement vanished without a word.
    """
    bi = parse_ensite_map_pp(_cfe_export("bi", 0.25))[0]
    uni = parse_ensite_map_pp(_cfe_export("uni", 0.75))[0]

    assert bi.get("cfe_mean") == 0.25
    assert bi.measurements["cfe_mean"].kind == "cfe_mean"
    # The bipolar name is unsuffixed: renaming it would rename the field in
    # every study already imported.
    assert "cfe_mean_uni" not in bi.measurements

    assert uni.get("cfe_mean_uni") == 0.75
    assert uni.measurements["cfe_mean_uni"].kind == "cfe_mean"
    assert "cfe_mean" not in uni.measurements


def test_voltage_keeps_polarity_in_the_kind_and_is_not_suffixed():
    """``PP`` is the exception: its polarity *is* the quantity."""
    from pulse_ep.core.importers.ensite import _dxl_measurement_name, _dxl_quantity

    for map_type, expected in (("PP_bi", "voltage_bipolar"), ("PP_uni", "voltage_unipolar")):
        kind = _dxl_quantity(map_type)
        assert kind == expected
        assert _dxl_measurement_name(map_type, kind, "P-P") == expected


def test_polarity_is_decoded_in_one_place_only():
    """`split_polarity` is the single decoder — the DxL header follows it too."""
    from pulse_ep.core.importers.ensite import _dxl_quantity, split_polarity

    # The tolerant suffix pattern that filenames get, applied to `Map type:`.
    assert split_polarity("CFEmean_bpolar") == ("CFEmean", "bipolar")
    assert _dxl_quantity("PP_bpolar") == "voltage_bipolar"
