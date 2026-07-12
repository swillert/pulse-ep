"""Points wiring: prepare detects Map_PP siblings, commit attaches them."""

from __future__ import annotations

from pulse_ep.core.importers.ensite import EnsiteImporter
from pulse_ep.core.importers.source import DirSource

_DIF = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<DIF><DIFHeader><Version>SJM_DIF_5.0</Version></DIFHeader><DIFBody>"
    '<Volumes number="1"><Volume name="S">'
    '<Vertices number="4"> 0 0 0  1 0 0  0 1 0  1 1 0 </Vertices>'
    '<Polygons number="2"> 1 2 3  2 4 3 </Polygons>'
    '<Map_data number="4"> 0.5 1.5 2.5 3.5 </Map_data>'
    "</Volume></Volumes></DIFBody></DIF>"
)

_HDR = (
    "Rov trace,Electrodes,Channels,Freeze Grp #,(Point #),Ref trace, Ref2 trace,"
    "roving x,roving y,roving z,surface x,surface y,surface z,normal x,normal y,normal z,"
    "displayed,utilized,gold-starred,P-P,P-P valid,refTime (abs),adjTime (ms),"
    "left curtain (ms),right curtain (ms),force (g),actSeq, annot"
)
_MAP_PP = (
    "Export Data Element: DxL\nMap type:,PP_bi\nData starts in row,4\n"
    f"{_HDR}\n"
    "T,A1 A2,c,1,37,..,..,49.8,-208.3,391.6,42.0,-215.2,392.0,-0.7,-0.7,0.0,1,0,0,0.965,1,0,8,20,319,3.2,10000,\n"
    "T,A1 B1,c,1,38,..,..,49.8,-208.3,391.6,43.0,-216.2,393.0,-0.7,-0.7,0.0,1,0,0,0.500,1,0,12,20,319,3.0,10000,\n"
)


def _make_export(root):
    (root / "Contact_Mapping_Model.xml").write_text(_DIF)
    cm = root / "Contact_Mapping"
    cm.mkdir()
    (cm / "Map_PP_bi.csv").write_text(_MAP_PP)
    (root / "AutoMark_Data.csv").write_text(
        "Exported from Software Version: 6.0\nExport from Study: s-1\n"
    )


def test_prepare_detects_points_file(tmp_path):
    _make_export(tmp_path)
    plan = EnsiteImporter().prepare(DirSource(tmp_path))
    mp = plan.studies[0].maps[0]
    assert mp.points_files == ["Contact_Mapping/Map_PP_bi.csv"]
    assert mp.include_points is True


def test_commit_attaches_measurement_points(tmp_path):
    _make_export(tmp_path)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()
    study = imp.commit(imp.prepare(src), src)[0]

    ep = study.epmaps[0]
    assert len(ep.measurement_points) == 2
    p0 = ep.measurement_points[0]
    assert p0.get("voltage_bipolar") == 0.965
    assert p0.get("contact_force") == 3.2
    assert "A1 A2" in p0.electrodes


def test_opt_out_of_points(tmp_path):
    _make_export(tmp_path)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()
    plan = imp.prepare(src)
    plan.studies[0].maps[0].include_points = False
    ep = imp.commit(plan, src)[0].epmaps[0]
    assert ep.measurement_points == []
