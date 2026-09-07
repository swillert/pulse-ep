"""EnSite X DIF parser + descriptor decoder (synthetic fixtures only)."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import (
    dif_to_epmap,
    parse_dif,
    parse_map_descriptor,
)
from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR, VOLTAGE_UNIPOLAR


def _dif(volumes_xml: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<DIF><DIFHeader><Version>SJM_DIF_5.0</Version></DIFHeader>"
        f"<DIFBody><Volumes number='1'>{volumes_xml}</Volumes></DIFBody></DIF>"
    ).encode()


# 4 vertices, 2 triangles — polygons written 1-BASED as EnSite does
_ONE_VOLUME = """
<Volume name="Surface1">
  <Vertices number="4"> 0 0 0  1 0 0  0 1 0  1 1 0 </Vertices>
  <Polygons number="2"> 1 2 3  2 4 3 </Polygons>
  <Normals number="4"> 0 0 1 0 0 1 0 0 1 0 0 1 </Normals>
  <Map_data number="4"> 0.5 1.5 2.5 3.5 </Map_data>
  <Map_status number="4"> 0 0 2 0 </Map_status>
  <Color_high_low number="2"> 0.1 1.5 </Color_high_low>
  <Rotation> 1 0 0 0 1 0 0 0 1 </Rotation>
  <Translation> 0 0 0 </Translation>
</Volume>
"""


def test_parse_dif_basic_shapes():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    assert vol.vertices.shape == (4, 3)
    assert vol.triangles.shape == (2, 3)
    assert vol.normals.shape == (4, 3)
    np.testing.assert_array_equal(vol.map_data, [0.5, 1.5, 2.5, 3.5])
    assert vol.color_high_low == (0.1, 1.5)


def test_polygons_are_converted_to_zero_based():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    # 1-based input {1..4} → 0-based {0..3}; must index vertices validly
    assert vol.triangles.min() == 0
    assert vol.triangles.max() == vol.vertices.shape[0] - 1
    np.testing.assert_array_equal(vol.triangles[0], [0, 1, 2])


def test_map_status_becomes_validity_mask():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    # status 0=valid, 2=interpolated → third vertex invalid
    np.testing.assert_array_equal(vol.status_mask, [True, True, False, True])


def test_view_matrix_not_applied_registration_kept():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    # coordinates stored raw (identity rotation kept as metadata)
    np.testing.assert_array_equal(vol.vertices[1], [1, 0, 0])
    np.testing.assert_array_equal(vol.rotation, [1, 0, 0, 0, 1, 0, 0, 0, 1])


def test_multiple_volumes():
    two = _ONE_VOLUME + _ONE_VOLUME.replace('name="Surface1"', 'name="Right"')
    vols = parse_dif(_dif(two))
    assert len(vols) == 2 and {v.name for v in vols} == {"Surface1", "Right"}


def test_descriptor_tolerant_decoding():
    d1 = parse_map_descriptor("Contact_Mapping_Model_Endo_Voltage_Pre-bi.xml")
    assert d1["part"] == "endo" and d1["polarity"] == "bipolar"
    assert "voltage" in d1.get("type_tokens", [])

    d2 = parse_map_descriptor("Contact_Mapping_Model_PreMap-unipolar.xml")
    assert d2["polarity"] == "unipolar"
    assert d2["raw_name"] == "Contact_Mapping_Model_PreMap-unipolar"


def test_dif_to_epmap_registers_voltage_with_mask():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    desc = parse_map_descriptor("Contact_Mapping_Model_Endo_Voltage_Pre-bi.xml")
    epmap = dif_to_epmap(vol, desc, study_name="s", source="ensite/6.0")

    field = epmap.get_field("voltage_bipolar")
    assert field.kind == VOLTAGE_BIPOLAR and field.unit == "mV"
    np.testing.assert_array_equal(field.status_mask, [True, True, False, True])
    np.testing.assert_array_equal(epmap.get_scalar("voltage_bipolar"), [0.5, 1.5, 2.5, 3.5])


def test_dif_to_epmap_unipolar_kind():
    (vol,) = parse_dif(_dif(_ONE_VOLUME))
    desc = parse_map_descriptor("Contact_Mapping_Model_ReMap-unipolar.xml")
    epmap = dif_to_epmap(vol, desc, study_name="s", source="ensite")
    assert epmap.get_field("voltage_unipolar").kind == VOLTAGE_UNIPOLAR
