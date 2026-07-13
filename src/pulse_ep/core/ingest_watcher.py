"""Watch a drop directory for new export bundles and enqueue them.

An export lands as a top-level folder or ZIP in the drop directory (via FTP,
SMB, rsync, or the web upload). A bundle is enqueued only once it is *ready* —
either a sibling ``<name>.done`` marker exists, or the bundle has been
quiescent (nothing changed) for a grace period — so a still-uploading
multi-GB export is never grabbed half-written. Already-seen bundles (by path)
are skipped, so scanning is idempotent.
"""

from __future__ import annotations

import time
from pathlib import Path

from pulse_ep.core.ingest_queue import enqueue
from pulse_ep.core.models import ImportJobModel


def _bundle_mtime(path: Path) -> float:
    if path.is_file():
        return path.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    return max(mtimes) if mtimes else path.stat().st_mtime


def _is_ready(path: Path, quiescence_seconds: float, require_marker: bool, now: float) -> bool:
    if require_marker:
        return (path.parent / (path.name + ".done")).exists()
    return (now - _bundle_mtime(path)) >= quiescence_seconds


def discover_bundles(
    drop_dir,
    quiescence_seconds: float = 5.0,
    require_marker: bool = False,
    now: float | None = None,
) -> list[str]:
    """Ready bundle paths (top-level folders + ``.zip`` files) in ``drop_dir``."""
    root = Path(drop_dir)
    if not root.is_dir():
        return []
    now = time.time() if now is None else now
    bundles: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or entry.name.endswith(".done"):
            continue
        if not (entry.is_dir() or entry.suffix.lower() == ".zip"):
            continue  # loose files aren't bundles
        if _is_ready(entry, quiescence_seconds, require_marker, now):
            bundles.append(str(entry))
    return bundles


def scan_and_enqueue(
    session,
    drop_dir,
    quiescence_seconds: float = 5.0,
    require_marker: bool = False,
    now: float | None = None,
) -> list[ImportJobModel]:
    """Enqueue every ready, not-yet-seen bundle in the drop directory."""
    ready = discover_bundles(drop_dir, quiescence_seconds, require_marker, now)
    seen = {j.source_path for j in session.query(ImportJobModel).all()}
    return [enqueue(session, path) for path in ready if path not in seen]
