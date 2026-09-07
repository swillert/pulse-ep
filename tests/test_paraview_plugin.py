"""The ParaView plugin must stay loadable and keep its property contract.

ParaView is not a test dependency — it ships its own Python and is installed
separately — so these checks read the plugin as source. That is enough to
catch the things that actually break a plugin: a renamed proxy, a property
that disappeared, or a password that crept into one.

The plugin is exercised against a real ParaView in the full-stack run, not
here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "examples" / "paraview" / "pulse_ep_plugin.py"


@pytest.fixture(scope="module")
def tree():
    if not PLUGIN.is_file():
        pytest.skip(f"plugin missing: {PLUGIN}")
    return ast.parse(PLUGIN.read_text(encoding="utf-8"))


def _decorator_names(node):
    names = []
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        names.append(ast.unparse(target))
    return names


def _source_class(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(
            d.startswith("smproxy.source") for d in _decorator_names(node)
        ):
            return node
    return None


def test_it_is_valid_python(tree):
    assert tree is not None


def test_registers_a_source_proxy(tree):
    cls = _source_class(tree)
    assert cls is not None, "no class decorated with @smproxy.source"
    # The README tells users these two names; ParaView derives the scripting
    # function `pulseepMap` from the label, so both are part of the contract.
    src = PLUGIN.read_text(encoding="utf-8")
    assert 'name="PulseEPMapSource"' in src
    assert 'label="pulse-ep Map"' in src


def test_exposes_the_documented_properties(tree):
    cls = _source_class(tree)
    setters = {
        n.name
        for n in cls.body
        if isinstance(n, ast.FunctionDef)
        and any(d.startswith("smproperty.") for d in _decorator_names(n))
    }
    assert setters == {
        "SetServerURL",
        "SetUsername",
        "SetMapID",
        "SetScalarName",
        "SetDistance",
        "SetRepresentation",
    }


def test_the_password_is_never_a_property(tree):
    """A property value lands in state files and traces; a password must not."""
    cls = _source_class(tree)
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(d.startswith("smproperty.") for d in _decorator_names(node)):
            assert "password" not in node.name.lower()
    src = PLUGIN.read_text(encoding="utf-8")
    assert 'os.environ.get("PULSE_EP_PASSWORD"' in src


def test_produces_polydata_and_implements_requestdata(tree):
    cls = _source_class(tree)
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "RequestData" in methods
    assert 'outputType="vtkPolyData"' in PLUGIN.read_text(encoding="utf-8")


def test_ssl_import_is_guarded(tree):
    """Several ParaView builds ship a Python without _ssl; an unguarded
    import makes the plugin unloadable there."""
    src = PLUGIN.read_text(encoding="utf-8")
    assert "try:\n    import ssl\nexcept ImportError:" in src


def test_scalar_name_is_optional_so_the_server_resolves_it(tree):
    """Guessing a field name breaks across vendors — the server knows."""
    src = PLUGIN.read_text(encoding="utf-8")
    assert "if scalar_name:" in src
    assert 'mesh.get("scalar_name")' in src
