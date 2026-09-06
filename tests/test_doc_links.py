"""Relative links in the top-level docs must point at files that exist.

The fixture README was linked from README.md and from the docs while it was
not in the repository at all — a `rm -rf` on its parent had removed it before
it was ever committed, and nothing noticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCS = [REPO / "README.md", REPO / "ARCHITECTURE.md", *sorted((REPO / "docs").rglob("*.md"))]

# [text](target) — skip URLs, anchors and mail links; keep relative paths.
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _relative_targets(path: Path):
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        yield target


@pytest.mark.parametrize("doc", [d for d in DOCS if d.is_file()], ids=lambda d: d.name)
def test_relative_links_resolve(doc):
    missing = [
        target
        for target in _relative_targets(doc)
        if not (doc.parent / target).exists() and not (REPO / target).exists()
    ]
    assert not missing, f"{doc.relative_to(REPO)} links to missing files: {missing}"
