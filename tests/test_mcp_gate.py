"""A deployment decides whether it is reachable by an AI client at all.

Without this the decision lived only with whoever starts the MCP server — a
copied config or an inherited machine, and the deployment had no say.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "flask", reason="the server is an optional extra: pip install 'pulse-ep[server]'"
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PULSE_EP_JWT_SECRET_KEY", "test-only")
    from pulse_ep.server import app as app_module

    app_module.app.config.update(TESTING=True)
    return app_module, app_module.app.test_client()


def _settings(enabled: bool):
    from types import SimpleNamespace

    return SimpleNamespace(mcp_enabled=enabled)


def test_an_mcp_request_is_refused_where_the_deployment_says_no(client, monkeypatch):
    app_module, http = client
    monkeypatch.setattr(app_module, "get_settings", lambda: _settings(False))

    response = http.get(
        "/list_studies", headers={app_module.MCP_CLIENT_HEADER: f"{app_module.MCP_CLIENT_NAME}/0.2"}
    )
    assert response.status_code == 403
    assert "MCP access is disabled" in response.get_json()["error"]
    # the refusal happens before authentication: an expired token is not the
    # reason a switched-off deployment says no
    assert "hint" in response.get_json()


def test_the_same_request_passes_the_gate_when_it_is_on(client, monkeypatch):
    app_module, http = client
    monkeypatch.setattr(app_module, "get_settings", lambda: _settings(True))

    response = http.get(
        "/list_studies", headers={app_module.MCP_CLIENT_HEADER: f"{app_module.MCP_CLIENT_NAME}/0.2"}
    )
    # past the gate, into ordinary authentication (no token was sent)
    assert response.status_code == 401


def test_other_clients_are_not_affected_by_the_switch(client, monkeypatch):
    """The viewer and the example clients keep working when MCP is off."""
    app_module, http = client
    monkeypatch.setattr(app_module, "get_settings", lambda: _settings(False))

    assert http.get("/list_studies").status_code == 401  # no MCP header: ordinary auth
    assert http.get("/login").status_code == 200  # the UI is untouched
