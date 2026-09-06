"""EnSite bi/uni grouping into one multi-scalar map, with a geometry guard."""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.importers.ensite import (
    DifVolume,
    GeometryMismatch,
    group_dif_files,
    group_key,
    merge_dif_group,
    parse_map_descriptor,
    split_polarity,
)

_VERTS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=float)
_TRIS = np.array([[0, 1, 2], [1, 3, 2]])


def _vol(map_data, verts=_VERTS):
    return DifVolume(
        name="v",
        vertices=verts,
        triangles=_TRIS,
        map_data=np.asarray(map_data, dtype=float),
        status_mask=np.ones(len(verts), dtype=bool),
    )


def test_group_key_strips_polarity():
    assert (
        group_key("Contact_Mapping_Model_Endo_Voltage_Pre-bi.xml")
        == "Contact_Mapping_Model_Endo_Voltage_Pre"
    )
    assert group_key("Contact_Mapping_Model_PreMap-unipolar.xml") == "Contact_Mapping_Model_PreMap"


def test_group_dif_files_pairs_bi_and_uni():
    names = [
        "M_Voltage_Pre-bi.xml",
        "M_Voltage_Pre-uni.xml",
        "M_ReMap-bipolar.xml",
        "M_ReMap-unipol.xml",
    ]
    groups = group_dif_files(names)
    assert set(groups) == {"M_Voltage_Pre", "M_ReMap"}
    assert len(groups["M_Voltage_Pre"]) == 2 and len(groups["M_ReMap"]) == 2


def test_group_key_is_case_insensitive():
    """One study exported the same map as ``RVStimPre-uni`` and ``RvStimPre-bi``."""
    names = ["M_RVStimPre-unipolar.xml", "M_RvStimPre-bipolar.xml"]
    groups = group_dif_files(names)
    assert len(groups) == 1
    assert sorted(next(iter(groups.values()))) == sorted(names)
    # the key keeps the first file's spelling rather than a casefolded one
    assert next(iter(groups)) == "M_RVStimPre"


def test_polarity_suffix_tolerates_missing_letter():
    """``-bpolar`` is a real operator typo; it must still pair with ``-unipolar``."""
    assert split_polarity("M_VT-bpolar") == ("M_VT", "bipolar")
    assert split_polarity("M_VT-unipolar") == ("M_VT", "unipolar")
    groups = group_dif_files(["M_VT-bpolar.xml", "M_VT-unipolar.xml"])
    assert set(groups) == {"M_VT"} and len(groups["M_VT"]) == 2


def test_descriptor_polarity_agrees_with_grouping():
    """A typo must not silently fall through to the bipolar default."""
    assert parse_map_descriptor("Contact_Mapping_Model_VT-bpolar.xml")["polarity"] == "bipolar"
    assert parse_map_descriptor("Contact_Mapping_Model_VT-unipolar.xml")["polarity"] == "unipolar"


def test_unpaired_map_keeps_its_own_group():
    groups = group_dif_files(["M_VT-unipolar.xml", "M_Other-bipolar.xml"])
    assert set(groups) == {"M_VT", "M_Other"}


def test_merge_bi_uni_into_one_map():
    items = [
        ("M_Voltage_Pre-bi.xml", _vol([0.5, 1.0, 1.5, 2.0])),
        ("M_Voltage_Pre-uni.xml", _vol([5.0, 6.0, 7.0, 8.0])),
    ]
    epmap = merge_dif_group(items, study_name="s", source="ensite")
    assert epmap.map_name == "M_Voltage_Pre"
    assert set(epmap.scalar_fields) == {"voltage_bipolar", "voltage_unipolar"}
    np.testing.assert_array_equal(epmap.get_scalar("voltage_bipolar"), [0.5, 1.0, 1.5, 2.0])
    np.testing.assert_array_equal(epmap.get_scalar("voltage_unipolar"), [5.0, 6.0, 7.0, 8.0])


def test_merge_rejects_geometry_mismatch():
    other = _vol([1.0, 2.0, 3.0, 4.0, 5.0], verts=np.zeros((5, 3)))
    with pytest.raises(GeometryMismatch):
        merge_dif_group(
            [("a-bi.xml", _vol([1, 2, 3, 4])), ("b-uni.xml", other)],
            study_name="s",
            source="x",
        )
