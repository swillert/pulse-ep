"""The MCP names itself, so a deployment can see it and refuse it.

Anything the MCP can do, a user with the same credentials can do with ``curl``
— so this is a gate, not a boundary. What it stops is the case that actually
happens: an MCP left running against a deployment that no longer wants one.
"""

from __future__ import annotations

import pytest

from pulse_ep.mcp.client import CLIENT_HEADER, CLIENT_NAME, MCPDisabled, PulseEpClient, PulseEpError


class _Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = str(self._body)
        self.content = b""

    def json(self):
        return self._body


class _Session:
    """Records what was sent, answers what the test set up."""

    def __init__(self, *responses):
        self.sent = []
        self._responses = list(responses) or [_Response()]

    def request(self, method, url, headers=None, **kwargs):
        self.sent.append({"method": method, "url": url, "headers": headers or {}})
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    def post(self, *a, **k):  # pragma: no cover - login is not under test here
        raise AssertionError("a configured token needs no login")


def _client(*responses, token="t"):
    client = PulseEpClient(base_url="http://server", token=token)
    client._session = _Session(*responses)
    return client


def test_every_request_says_what_it_is():
    client = _client()
    client.get_json("/list_studies")

    header = client._session.sent[0]["headers"][CLIENT_HEADER]
    assert header.startswith(f"{CLIENT_NAME}/")
    assert client._session.sent[0]["headers"]["Authorization"] == "Bearer t"


def test_a_refusal_is_reported_as_the_deployment_s_decision():
    client = _client(_Response(403, {"error": "MCP access is disabled on this deployment"}))
    with pytest.raises(MCPDisabled, match="does not serve MCP access"):
        client.get_json("/list_studies")


def test_an_ordinary_403_is_still_an_ordinary_error():
    """Only the deployment switch gets the special report."""
    client = _client(_Response(403, {"msg": "admin only"}))
    with pytest.raises(PulseEpError) as raised:
        client.get_json("/epmaps/set_attributes")
    assert not isinstance(raised.value, MCPDisabled)
    assert "admin only" in str(raised.value)
