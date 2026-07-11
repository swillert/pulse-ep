"""Transport-neutral import source (dir / zip) + vendor auto-detection."""

from __future__ import annotations

import zipfile

from pulse_ep.core.importers.base import detect_vendor
from pulse_ep.core.importers.source import DirSource, ZipSource, source_for


def _make_tree(root):
    (root / "sub").mkdir()
    (root / "Study.xml").write_text("<Study/>")
    (root / "sub" / "1-Map.mesh").write_text("#TriangulatedMeshVersion2.0")
    (root / "._junk").write_text("applemeta")  # must be ignored


def test_dirsource_list_open_materialize(tmp_path):
    _make_tree(tmp_path)
    src = DirSource(tmp_path)
    names = src.list()
    assert "Study.xml" in names and "sub/1-Map.mesh" in names
    assert "._junk" not in names  # AppleDouble skipped
    assert src.list("*.mesh") == ["sub/1-Map.mesh"]
    with src.open("Study.xml") as fh:
        assert fh.read() == b"<Study/>"
    # a directory materialises to itself
    assert src.materialize() == tmp_path.resolve()


def test_zipsource_list_open_and_selective_materialize(tmp_path):
    _make_tree(tmp_path)
    zip_path = tmp_path.parent / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(tmp_path / "Study.xml", "Study.xml")
        zf.write(tmp_path / "sub" / "1-Map.mesh", "sub/1-Map.mesh")

    src = ZipSource(zip_path)
    assert set(src.list()) == {"Study.xml", "sub/1-Map.mesh"}
    with src.open("sub/1-Map.mesh") as fh:
        assert fh.read().startswith(b"#TriangulatedMeshVersion2.0")

    # selective materialize: extract only the mesh, not the whole archive
    out = src.materialize(members=["sub/1-Map.mesh"])
    assert (out / "sub" / "1-Map.mesh").is_file()
    assert not (out / "Study.xml").exists()
    src.close()


def test_source_for_dispatches(tmp_path):
    _make_tree(tmp_path)
    assert isinstance(source_for(tmp_path), DirSource)
    zip_path = tmp_path.parent / "e2.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.mesh", "x")
    assert isinstance(source_for(zip_path), ZipSource)


def test_detect_vendor_carto_by_mesh(tmp_path):
    # a source containing .mesh files is recognised as CARTO
    _make_tree(tmp_path)
    importer = detect_vendor(DirSource(tmp_path))
    assert importer is not None and importer.name == "carto"


def test_detect_vendor_none_without_mesh(tmp_path):
    (tmp_path / "Contact_Mapping_Model.xml").write_text("<DIF/>")  # EnSite-ish, no .mesh
    # no EnSite importer registered yet, and CARTO needs .mesh → no match
    assert detect_vendor(DirSource(tmp_path)) is None
