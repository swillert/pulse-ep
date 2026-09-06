"""Every console script the package installs must actually be callable.

Three were not: ``pulse-ep-populate-colormaps`` pointed at a ``main`` that did
not exist, ``pulse-ep-extract-meshes`` ran its whole body at import time — so
it demanded a database connection just to be imported — and
``pulse-ep-tag-maps`` parsed ``sys.argv`` at import, which made argparse read
the importing program's arguments and exit. All three failed only once
installed, which is exactly where nothing was looking.

The entry points are read from installed metadata rather than parsed out of
``pyproject.toml``, so this checks the reality a user gets.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import pytest


def _console_scripts() -> dict[str, str]:
    """Installed ``pulse-ep-*`` console scripts, name -> "module:attr"."""
    scripts = entry_points(group="console_scripts")
    return {ep.name: ep.value for ep in scripts if ep.name.startswith("pulse-ep-")}


_SCRIPTS = _console_scripts()


@pytest.mark.skipif(not _SCRIPTS, reason="pulse-ep is not installed")
@pytest.mark.parametrize("name", sorted(_SCRIPTS))
def test_console_script_loads(name):
    """Resolving an entry point imports its module and fetches the attribute,
    so this fails on a missing ``main`` and on any import-time side effect
    that needs a database or a command line."""
    ep = next(e for e in entry_points(group="console_scripts") if e.name == name)
    assert callable(ep.load()), f"{name} -> {ep.value} is not callable"


@pytest.mark.skipif(not _SCRIPTS, reason="pulse-ep is not installed")
def test_the_expected_scripts_are_installed():
    """A renamed or dropped entry point should fail loudly, not silently."""
    assert {"pulse-ep-server", "pulse-ep-demo", "pulse-ep-import-carto"} <= set(_SCRIPTS)
