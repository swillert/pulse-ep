"""Transport-neutral access to an import's files.

Decouples vendor importers from *how* bytes arrive: a local directory, a
ZIP, or an uploaded temp file all present the same ``list`` / ``open`` /
``materialize`` interface. Parsing never assumes a local filesystem layout,
so the upload / chunked / async machinery can sit in front unchanged.

``materialize`` exists because the current path-based CARTO/EnSite readers
take file paths: a ZIP is (selectively) extracted to a temp dir once, then
the existing readers run on it — avoiding a stream rewrite of lxml/mesh I/O.

Container detection goes by *content*, never by filename: real CARTO exports
arrive named ``.zip`` while actually being 7-Zip archives, and a name-based
check rejects them outright.
"""

from __future__ import annotations

import fnmatch
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class ImportSource(Protocol):
    def list(self, pattern: str | None = None) -> list[str]:
        """Relative member names, optionally filtered by an fnmatch pattern."""
        ...

    def open(self, name: str) -> BinaryIO:
        """Open one member as a binary stream (no full extraction)."""
        ...

    def size(self, name: str) -> int:
        """Uncompressed byte size of a member (no extraction)."""
        ...

    def materialize(self, members: list[str] | None = None) -> Path:
        """Ensure the (selected) members exist as a local directory tree."""
        ...


def _visible(name: str) -> bool:
    # skip directories and macOS AppleDouble metadata
    return not name.endswith("/") and not Path(name).name.startswith("._")


class DirSource:
    """An import already present as a local directory."""

    def __init__(self, path: str | Path) -> None:
        self.root = Path(path).expanduser().resolve()

    def list(self, pattern: str | None = None) -> list[str]:
        names = [
            str(p.relative_to(self.root))
            for p in self.root.rglob("*")
            if p.is_file() and _visible(p.name)
        ]
        if pattern:
            names = [n for n in names if fnmatch.fnmatch(n, pattern)]
        return sorted(names)

    def open(self, name: str) -> BinaryIO:
        return open(self.root / name, "rb")

    def size(self, name: str) -> int:
        return (self.root / name).stat().st_size

    def materialize(self, members: list[str] | None = None) -> Path:
        return self.root


class ZipSource:
    """An import delivered as a ZIP (drag & drop / upload)."""

    def __init__(self, zip_path: str | Path) -> None:
        self.zip_path = Path(zip_path).expanduser().resolve()
        self._zf = zipfile.ZipFile(self.zip_path)

    def list(self, pattern: str | None = None) -> list[str]:
        names = [n for n in self._zf.namelist() if _visible(n)]
        if pattern:
            names = [n for n in names if fnmatch.fnmatch(n, pattern)]
        return sorted(names)

    def open(self, name: str) -> BinaryIO:
        return self._zf.open(name)

    def size(self, name: str) -> int:
        return self._zf.getinfo(name).file_size

    def materialize(self, members: list[str] | None = None, dest: str | Path | None = None) -> Path:
        """Extract selected members (or all) to a temp dir; return its path.

        Passing ``members`` (e.g. only the DIF meshes + point tables) keeps a
        multi-GB archive from being fully unpacked.
        """
        out = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="pulse_ep_import_"))
        for name in members if members is not None else self.list():
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._zf.open(name) as src, open(target, "wb") as fh:
                shutil.copyfileobj(src, fh)
        return out

    def close(self) -> None:
        self._zf.close()


#: 7-Zip archives start with these six bytes, whatever the file is named.
_SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"


def is_7zfile(path: str | Path) -> bool:
    """True if ``path`` is a 7-Zip archive, by signature rather than suffix."""
    try:
        with open(path, "rb") as fh:
            return fh.read(6) == _SEVENZIP_MAGIC
    except OSError:
        return False


class SevenZipSource:
    """An import delivered as a 7-Zip archive.

    CARTO exports are routinely named ``.zip`` while actually being 7-Zip
    containers, so this is not an exotic case — without it such an export
    cannot be read at all.

    7-Zip has no per-member random access: a member is reached by
    decompressing its block. Reading members one at a time would therefore
    re-decompress repeatedly, so this extracts once, lazily, on first access
    and serves everything from that temp directory.
    """

    def __init__(self, path: str | Path) -> None:
        self.archive_path = Path(path).expanduser().resolve()
        self._extracted: Path | None = None
        try:
            import py7zr  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ValueError(
                f"{self.archive_path} is a 7-Zip archive; install the 'py7zr' package "
                "to import it (pip install 'pulse-ep[sevenzip]')"
            ) from exc

    def _root(self) -> Path:
        """Extract once on first use; later calls reuse the temp directory."""
        if self._extracted is None:
            import py7zr

            dest = Path(tempfile.mkdtemp(prefix="pulse_ep_7z_"))
            with py7zr.SevenZipFile(self.archive_path, "r") as z:
                z.extractall(path=dest)
            self._extracted = dest
        return self._extracted

    def list(self, pattern: str | None = None) -> list[str]:
        # Names come from the archive index — no extraction needed to list.
        import py7zr

        with py7zr.SevenZipFile(self.archive_path, "r") as z:
            names = [n for n in z.getnames() if not Path(n).name.startswith("._")]
        if pattern:
            names = [n for n in names if fnmatch.fnmatch(n, pattern)]
        return sorted(names)

    def open(self, name: str) -> BinaryIO:
        return open(self._root() / name, "rb")

    def size(self, name: str) -> int:
        return (self._root() / name).stat().st_size

    def materialize(self, members: list[str] | None = None) -> Path:
        return self._root()


def source_for(path: str | Path) -> ImportSource:
    """Return the :class:`ImportSource` matching ``path``'s actual container.

    Detection is by content, not by suffix — see the module docstring.
    """
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        return DirSource(p)
    if zipfile.is_zipfile(p):
        return ZipSource(p)
    if is_7zfile(p):
        return SevenZipSource(p)
    raise ValueError(f"Unsupported import source (not a directory, ZIP or 7-Zip archive): {p}")
