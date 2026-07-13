"""Drop-directory watcher: readiness (quiescence / marker) + bundle selection."""

from __future__ import annotations

import os

from pulse_ep.core.ingest_watcher import discover_bundles

_NOW = 1000.0


def _touch(path, mtime):
    path.write_text("x")
    os.utime(path, (mtime, mtime))


def test_quiescent_bundle_ready_but_fresh_not(tmp_path):
    old = tmp_path / "export_old"
    old.mkdir()
    _touch(old / "f.xml", _NOW - 10)  # last change 10 s ago
    fresh = tmp_path / "export_fresh"
    fresh.mkdir()
    _touch(fresh / "f.xml", _NOW - 1)  # still being written

    ready = discover_bundles(tmp_path, quiescence_seconds=5, now=_NOW)
    assert str(old) in ready
    assert str(fresh) not in ready  # not quiescent yet


def test_zip_is_a_bundle(tmp_path):
    z = tmp_path / "export.zip"
    _touch(z, _NOW - 10)
    assert discover_bundles(tmp_path, quiescence_seconds=5, now=_NOW) == [str(z)]


def test_marker_mode_ignores_quiescence(tmp_path):
    b = tmp_path / "exp"
    b.mkdir()
    _touch(b / "f.xml", _NOW - 1)  # fresh, but a marker says it's done
    (tmp_path / "exp.done").write_text("")
    assert str(b) in discover_bundles(tmp_path, require_marker=True, now=_NOW)

    b2 = tmp_path / "exp2"
    b2.mkdir()
    _touch(b2 / "f.xml", _NOW - 100)  # old, but no marker
    assert str(b2) not in discover_bundles(tmp_path, require_marker=True, now=_NOW)


def test_skips_hidden_markers_and_loose_files(tmp_path):
    (tmp_path / ".hidden").mkdir()
    _touch(tmp_path / "loose.txt", _NOW - 10)  # a loose file, not a bundle
    (tmp_path / "exp.done").write_text("")  # a marker
    b = tmp_path / "exp"
    b.mkdir()
    _touch(b / "f.xml", _NOW - 10)

    assert discover_bundles(tmp_path, quiescence_seconds=5, now=_NOW) == [str(b)]
