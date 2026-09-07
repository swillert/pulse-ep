"""The MCP wiring: which tools exist, and — more importantly — which do not."""

from __future__ import annotations

import pytest

from pulse_ep.mcp.anonymize import Anonymiser
from pulse_ep.mcp.tools import Tools

pytest.importorskip("mcp", reason="the MCP SDK is an optional extra: pip install 'pulse-ep[mcp]'")

from pulse_ep.mcp.server import build_server, is_enabled, main  # noqa: E402

EXPECTED_TOOLS = {
    # summaries — answer a question
    "list_studies",
    "list_maps",
    "map_summary",
    "read_points",
    "area_of_range",
    "compare_maps",
    "list_waveforms",
    "read_waveform",
    # the complete data, written to a file next to the client
    "fetch_map",
    "fetch_points",
    "fetch_waveform",
}


def _tool_names(anonymized=True):
    server = build_server(Tools(object(), Anonymiser(enabled=anonymized)), anonymized)
    import anyio

    return {t.name for t in anyio.run(server.list_tools)}


def test_the_advertised_tools_are_the_ones_that_exist():
    assert _tool_names() == EXPECTED_TOOLS


def test_nothing_writes_and_nothing_imports():
    """Import, tagging and deletion stay where a person is present.

    ``fetch_*`` writes files, but only into the download directory, and
    changes nothing in the deployment.
    """
    forbidden = ("import", "delete", "set_", "update", "create", "tag")
    assert not [t for t in _tool_names() if t.startswith(forbidden)]


def test_no_tool_can_switch_anonymisation_off():
    """The protection is the operator's setting, not the model's option."""
    assert not [t for t in _tool_names() if "anonym" in t]


def test_the_instructions_state_the_mode():
    """A session that is not anonymised must say so where the client can see it."""
    anonymised = build_server(Tools(object(), Anonymiser()), True)
    plain = build_server(Tools(object(), Anonymiser(enabled=False)), False)
    assert "Study identity: anonymised." in anonymised.instructions
    assert "NOT anonymised" in plain.instructions


def test_check_reports_the_mode_and_exits(monkeypatch, capsys):
    """``--check`` is the "did I configure this right?" answer, before wiring it in."""
    monkeypatch.setenv("PULSE_EP_MCP_TOKEN", "t")
    monkeypatch.setattr(
        "pulse_ep.mcp.server.client_from_env",
        lambda env: _StubClient(),
    )
    assert main(["--enabled", "--check"]) == 0
    out = capsys.readouterr().out
    assert "anonymised: True" in out
    assert "study/12" in out
    assert "10054321" not in out


def test_check_without_anonymisation_warns_on_stderr(monkeypatch, capsys):
    monkeypatch.setattr("pulse_ep.mcp.server.client_from_env", lambda env: _StubClient())
    assert main(["--enabled", "--check", "--no-anonymize"]) == 0
    captured = capsys.readouterr()
    assert "anonymisation is OFF" in captured.err
    assert "10054321_XY_AB 01_02_2020 09-15-00" in captured.out  # the real name, as asked


class _StubClient:
    base_url = "http://localhost:5000"

    def studies(self):
        return [{"id": 12, "study_name": "10054321_XY_AB 01_02_2020 09-15-00", "vendor": "carto"}]


# --- switching it off --------------------------------------------------------


def test_serving_requires_explicit_opt_in():
    assert is_enabled({}) is False
    for on in ("1", "true", "yes", "on", "ON"):
        assert is_enabled({"PULSE_EP_MCP_ENABLED": on}) is True
    for off in ("", "0", "false", "no", "off", "OFF", "flase"):
        assert is_enabled({"PULSE_EP_MCP_ENABLED": off}) is False


def test_the_flag_wins_over_the_environment():
    assert is_enabled({"PULSE_EP_MCP_ENABLED": "0"}, override=True) is True
    assert is_enabled({}, override=False) is False


@pytest.mark.parametrize("value", [None, "0"])
def test_a_server_that_may_not_serve_starts_nothing_and_says_why(monkeypatch, capsys, value):
    """It must not start and then answer questions — and not look crashed.

    Unset is the case that matters: opt-in means an operator who never made
    the decision gets the same refusal as one who made it explicitly.
    """
    started = []
    monkeypatch.setattr(
        "pulse_ep.mcp.server.build_server", lambda *a, **k: started.append(a) or _NeverRun()
    )
    monkeypatch.delenv("PULSE_EP_MCP_ENABLED", raising=False)
    if value is not None:
        monkeypatch.setenv("PULSE_EP_MCP_ENABLED", value)

    assert main([]) == 0  # not serving on purpose is not a failure
    assert started == []
    # Says what to do, not merely that it did nothing.
    assert "PULSE_EP_MCP_ENABLED=1" in capsys.readouterr().err


def test_a_deployment_that_refuses_mcp_is_reported_as_that(monkeypatch, capsys):
    """Not as "403 on /list_studies" — the operator turned it off deliberately."""
    from pulse_ep.mcp.client import MCPDisabled

    class _Refusing:
        base_url = "http://server"

        def studies(self):
            raise MCPDisabled("http://server does not serve MCP access")

    monkeypatch.setattr("pulse_ep.mcp.server.client_from_env", lambda env: _Refusing())
    assert main(["--enabled", "--check"]) == 3  # its own exit code, distinct from a config error
    assert "does not serve MCP access" in capsys.readouterr().err


class _NeverRun:
    def run(self):  # pragma: no cover - reaching this is the failure
        raise AssertionError("a disabled server must not run")
