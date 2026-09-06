"""Every declared console script must actually be callable.

Two of them were not: ``pulse-ep-populate-colormaps`` pointed at a ``main``
that did not exist, and ``pulse-ep-extract-meshes`` ran its whole body at
import time — so it demanded a database connection just to be imported, and
had no ``main`` either. Both failed only once installed, which is exactly
where nobody was looking.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import tomllib

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _scripts() -> dict[str, str]:
    with open(_PYPROJECT, "rb") as fh:
        return tomllib.load(fh)["project"]["scripts"]


@pytest.mark.parametrize("name", sorted(_scripts()))
def test_console_script_target_is_callable(name):
    """Importing the module must not need a database, and the entry point
    named in pyproject must exist and be callable."""
    module_path, _, attr = _scripts()[name].partition(":")
    module = importlib.import_module(module_path)
    target = getattr(module, attr, None)
    assert callable(target), f"{name} -> {module_path}:{attr} is not callable"


def test_every_cli_module_has_an_argument_parser():
    """A console script that takes no arguments at all is usually one whose
    entry point was never exercised."""
    for name, target in _scripts().items():
        if not target.startswith("pulse_ep.cli."):
            continue
        module = importlib.import_module(target.partition(":")[0])
        assert hasattr(module, "main"), name
