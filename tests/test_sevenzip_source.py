"""7-Zip imports — detected by content, because CARTO mislabels them.

Real CARTO exports arrive named ``.zip`` while actually being 7-Zip
archives, so a suffix-based check rejects them outright and the export
cannot be imported at all.
"""

from __future__ import annotations

import pytest

from pulse_ep.core.importers.source import DirSource, ZipSource, is_7zfile, source_for

py7zr = pytest.importorskip("py7zr")


@pytest.fixture
def sevenzip_archive(tmp_path):
    """A 7-Zip archive deliberately named ``.zip``, as CARTO writes them."""
    src = tmp_path / "payload"
    (src / "sub").mkdir(parents=True)
    (src / "Study.xml").write_text("<Study name='S'/>")
    (src / "sub" / "1-LA.mesh").write_text("#TriangulatedMeshVersion2.0")
    archive = tmp_path / "Export_misnamed.zip"
    with py7zr.SevenZipFile(archive, "w") as z:
        z.writeall(src, arcname="")
    return archive


def test_a_7z_archive_named_zip_is_detected_by_content(sevenzip_archive):
    assert is_7zfile(sevenzip_archive) is True
    source = source_for(sevenzip_archive)
    assert type(source).__name__ == "SevenZipSource"


def test_listing_needs_no_extraction(sevenzip_archive):
    names = source_for(sevenzip_archive).list()
    assert any(n.endswith("Study.xml") for n in names)
    assert any(n.endswith("1-LA.mesh") for n in names)


def test_glob_filtering_matches_the_other_sources(sevenzip_archive):
    source = source_for(sevenzip_archive)
    assert [n for n in source.list("*.mesh")] == source.list("*.mesh")
    assert len(source.list("*.mesh")) == 1
    assert source.list("*.nope") == []


def test_open_and_size_read_through(sevenzip_archive):
    source = source_for(sevenzip_archive)
    name = next(n for n in source.list() if n.endswith("Study.xml"))
    assert b"<Study" in source.open(name).read()
    assert source.size(name) > 0


def test_materialize_yields_a_usable_directory(sevenzip_archive):
    root = source_for(sevenzip_archive).materialize()
    assert (root / "Study.xml").exists() or any(root.rglob("Study.xml"))


def test_a_carto_bundle_in_7z_form_is_recognised(sevenzip_archive):
    """The end that matters: vendor detection over a mislabelled archive."""
    from pulse_ep.core.importers.base import detect_vendor

    importer = detect_vendor(source_for(sevenzip_archive))
    assert importer is not None and importer.name == "carto"


def test_plain_zip_and_directory_are_unaffected(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.mesh").write_text("x")
    assert isinstance(source_for(d), DirSource)

    import zipfile

    z = tmp_path / "real.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.mesh", "x")
    assert isinstance(source_for(z), ZipSource)
    assert is_7zfile(z) is False


def test_an_unsupported_file_still_raises(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    with pytest.raises(ValueError, match="not a directory, ZIP or 7-Zip"):
        source_for(f)
