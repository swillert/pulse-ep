"""Model_Groups.xml -> geometry-only anatomy EPMaps (tagged as anatomy)."""

from __future__ import annotations

from pulse_ep.core.importers.ensite import EnsiteImporter
from pulse_ep.core.importers.source import DirSource

_MG = (
    '<?xml version="1.0"?><DIF><DIFHeader><Version>SJM_DIF_5.0</Version></DIFHeader><DIFBody>'
    '<Volumes number="2">'
    '<Volume name="Right"><Vertices number="4"> 0 0 0  1 0 0  0 1 0  1 1 0 </Vertices>'
    '<Polygons number="2"> 1 2 3  2 4 3 </Polygons></Volume>'
    '<Volume name="Left"><Vertices number="4"> 0 0 1  1 0 1  0 1 1  1 1 1 </Vertices>'
    '<Polygons number="2"> 1 2 3  2 4 3 </Polygons></Volume>'
    "</Volumes></DIFBody></DIF>"
)


def test_model_groups_become_anatomy_maps(tmp_path):
    (tmp_path / "Model_Groups.xml").write_text(_MG)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()

    plan = imp.prepare(src)
    assert plan.studies[0].anatomy_files == ["Model_Groups.xml"]

    study = imp.commit(plan, src)[0]
    anatomy = [e for e in study.epmaps if e.attributes.get("kind") == "anatomy"]
    assert len(anatomy) == 2
    chambers = {e.attributes["chamber"] for e in anatomy}
    assert chambers == {"Right", "Left"}
    # geometry-only: a mesh but no scalar fields
    a = anatomy[0]
    assert a.vertices.shape == (4, 3) and a.scalar_fields == {}
    assert a.map_name.startswith("Anatomy:")


def test_opt_out_of_anatomy(tmp_path):
    (tmp_path / "Model_Groups.xml").write_text(_MG)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()
    plan = imp.prepare(src)
    plan.studies[0].include_anatomy = False
    assert imp.commit(plan, src)[0].epmaps == []
