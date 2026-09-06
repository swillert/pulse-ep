"""EnsiteImporter: sniff / prepare (ImportPlan) / commit over an ImportSource."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.base import detect_vendor
from pulse_ep.core.importers.ensite import EnsiteImporter
from pulse_ep.core.importers.source import DirSource

_DIF = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<DIF><DIFHeader><Version>SJM_DIF_5.0</Version></DIFHeader><DIFBody>"
    '<Volumes number="1"><Volume name="S">'
    '<Vertices number="4"> 0 0 0  1 0 0  0 1 0  1 1 0 </Vertices>'
    '<Polygons number="2"> 1 2 3  2 4 3 </Polygons>'
    '<Map_data number="4"> {vals} </Map_data>'
    '<Map_status number="4"> 0 0 0 0 </Map_status>'
    "</Volume></Volumes></DIFBody></DIF>"
)


def _make_export(root):
    (root / "Contact_Mapping_Model_Endo_Voltage_Pre-bi.xml").write_text(
        _DIF.format(vals="0.5 1.0 1.5 2.0")
    )
    (root / "Contact_Mapping_Model_Endo_Voltage_Pre-uni.xml").write_text(
        _DIF.format(vals="5 6 7 8")
    )
    (root / "AutoMark_Data.csv").write_text(
        "Export File Version: 7.0\n"
        "Export Data Element: AutoMark_Data\n"
        "Exported from Software Version: 6.0.0.683129\n"
        "Export from Study: abc-123\n"
    )
    (root / "EP_Catheter_Bipolar_Waveforms_Filtered.csv").write_text("x" * 100)


def test_sniff_recognises_dif(tmp_path):
    _make_export(tmp_path)
    assert EnsiteImporter().sniff(DirSource(tmp_path)) is True


def test_detect_vendor_picks_ensite(tmp_path):
    _make_export(tmp_path)
    imp = detect_vendor(DirSource(tmp_path))
    assert imp is not None and imp.name == "ensite"


def test_prepare_builds_plan_with_defaults(tmp_path):
    _make_export(tmp_path)
    plan = EnsiteImporter().prepare(DirSource(tmp_path))

    assert len(plan.studies) == 1
    sp = plan.studies[0]
    assert sp.vendor == "ensite"
    assert sp.study_name == "abc-123"  # from CSV preamble GUID
    assert sp.provenance["software_version"] == "6.0.0.683129"

    # bi + uni collapse into one map with two scalar fields
    assert len(sp.maps) == 1
    mp = sp.maps[0]
    assert mp.map_name == "Contact_Mapping_Model_Endo_Voltage_Pre"
    assert mp.part == "endo"
    assert set(mp.scalar_fields) == {"voltage_bipolar", "voltage_unipolar"}
    assert mp.n_vertices == 4
    assert mp.include is True

    # waveforms detected but opt-in OFF, with a size estimate
    assert sp.waveforms.include is False
    assert any("Waveforms" in f for f in sp.waveforms.files)
    assert sp.waveforms.estimated_bytes == 100


def test_commit_builds_study_with_merged_map(tmp_path):
    _make_export(tmp_path)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()
    studies = imp.commit(imp.prepare(src), src)

    assert len(studies) == 1
    study = studies[0]
    assert study.vendor == "ensite"
    assert len(study.epmaps) == 1
    ep = study.epmaps[0]
    assert set(ep.scalar_fields) == {"voltage_bipolar", "voltage_unipolar"}
    np.testing.assert_array_equal(ep.get_scalar("voltage_bipolar"), [0.5, 1.0, 1.5, 2.0])
    np.testing.assert_array_equal(ep.get_scalar("voltage_unipolar"), [5.0, 6.0, 7.0, 8.0])
