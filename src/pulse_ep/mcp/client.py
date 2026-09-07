"""A thin REST client — the MCP server is a client like any other.

pulse-ep's surfaces (viewer, example clients, toolkit) are peers over the same
JWT REST API; there is no privileged internal path, and the MCP server does
not get one either. It talks HTTP to a running ``pulse-ep-server``, so it is
subject to the same authentication and sees exactly what a user with that
account sees — which is the point: a second, direct route into the database
would be a second set of rules to keep right.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

DEFAULT_BASE_URL = "http://localhost:5000"
DEFAULT_TIMEOUT = 60.0

#: Every request says what it is. A deployment can then see AI access in its
#: logs and refuse it (``PULSE_EP_MCP_ENABLED=0`` on the server), instead of
#: that decision living only with whoever starts this process.
CLIENT_HEADER = "X-Pulse-EP-Client"
CLIENT_NAME = "pulse-ep-mcp"


class PulseEpError(RuntimeError):
    """The server refused or could not answer a request."""


class MCPDisabled(PulseEpError):
    """The deployment does not serve MCP access."""


@dataclass
class PulseEpClient:
    """Authenticated access to a pulse-ep server."""

    base_url: str = DEFAULT_BASE_URL
    token: str | None = None
    username: str | None = None
    password: str | None = None
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._session = requests.Session()

    # -- plumbing ---------------------------------------------------------

    def login(self) -> str:
        """Exchange username/password for a JWT, if no token was configured."""
        if self.token:
            return self.token
        if not (self.username and self.password):
            raise PulseEpError(
                "no credentials: set PULSE_EP_MCP_TOKEN, or "
                "PULSE_EP_MCP_USERNAME and PULSE_EP_MCP_PASSWORD"
            )
        response = self._session.post(
            f"{self.base_url}/login_user",
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise PulseEpError(f"login failed ({response.status_code})")
        self.token = response.json().get("access_token")
        if not self.token:
            raise PulseEpError("login returned no access token")
        return self.token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.login()}",
            CLIENT_HEADER: f"{CLIENT_NAME}/{_version()}",
        }

    def request(self, method: str, path: str, **kwargs):
        """One authenticated call, retried once through a fresh login.

        A JWT expires, and an MCP server is long-lived — hours between two
        questions is normal — so the first 401 is a stale token, not a wrong
        password.
        """
        for attempt in (1, 2):
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
            if response.status_code == 401 and attempt == 1 and self.username:
                self.token = None  # expired — log in again and retry once
                continue
            break

        # A deployment that has switched MCP access off says so on every
        # request; report that as itself rather than as "403 on /list_studies".
        if response.status_code == 403 and "MCP access is disabled" in _message(response):
            raise MCPDisabled(
                f"{self.base_url} does not serve MCP access (PULSE_EP_MCP_ENABLED=0 on the server)"
            )
        if response.status_code >= 400:
            raise PulseEpError(f"{method} {path} -> {response.status_code}: {_message(response)}")
        return response

    def get_json(self, path: str, params: dict | None = None):
        return self.request("GET", path, params=params).json()

    def post_json(self, path: str, body: dict):
        return self.request("POST", path, json=body).json()

    # -- endpoints --------------------------------------------------------

    def studies(self) -> list[dict]:
        return self.get_json("/list_studies")

    def maps(self, study_id: int) -> list[dict]:
        return self.get_json(f"/list_epmaps_in_study/{int(study_id)}")

    def scalars(self, map_id: int) -> dict:
        return self.get_json(f"/epmaps/{int(map_id)}/scalars")

    def attributes(self, map_id: int) -> dict:
        return self.post_json("/epmaps/get_attributes", {"map_id": int(map_id)})

    def areas(self, map_id: int, intervals: list, scalar_name=None, distance=5) -> dict:
        return self.post_json(
            "/calculate_areas_for_intervals",
            {
                "map_id": int(map_id),
                "intervals": intervals,
                "scalar_name": scalar_name,
                "distance": distance,
            },
        )

    def compare(self, map_a_id: int, map_b_id: int, scalar_name: str, **options) -> dict:
        body = {
            "map_a_id": int(map_a_id),
            "map_b_id": int(map_b_id),
            "scalar_name": scalar_name,
            # Never the per-vertex field: tens of thousands of numbers are
            # useless to a reader and would swamp the conversation.
            "include_delta": False,
            **options,
        }
        return self.post_json("/api/compare", body)

    def points(self, map_id: int, limit: int = 500, offset: int = 0) -> dict:
        return self.get_json(
            f"/epmaps/{int(map_id)}/points", params={"limit": int(limit), "offset": int(offset)}
        )

    def mesh_raw(self, map_id: int, scalar_name: str | None = None) -> dict:
        """The complete stored map: mesh, every scalar field, points, signals.

        ``representation=raw`` is the export with no rendering applied — the
        same bytes an analysis client would work from.
        """
        params = {"map_id": int(map_id), "representation": "raw"}
        if scalar_name:
            params["scalar_name"] = scalar_name
        return self.get_json("/get_mesh_data", params=params)

    def waveforms(self, map_id: int) -> dict:
        return self.get_json(f"/epmaps/{int(map_id)}/waveforms")

    def waveform_bytes(self, waveform_id: int) -> bytes:
        return self.request("GET", f"/waveforms/{int(waveform_id)}/download").content


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("pulse-ep")
    except PackageNotFoundError:  # a source checkout without an install
        return "dev"


def _message(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:200]
    if isinstance(body, dict):
        return str(body.get("error") or body.get("msg") or body)[:200]
    return str(body)[:200]


def client_from_env(env) -> PulseEpClient:
    """Build a client from ``PULSE_EP_MCP_*`` configuration."""
    return PulseEpClient(
        base_url=env.get("PULSE_EP_MCP_BASE_URL") or DEFAULT_BASE_URL,
        token=env.get("PULSE_EP_MCP_TOKEN") or None,
        username=env.get("PULSE_EP_MCP_USERNAME") or None,
        password=env.get("PULSE_EP_MCP_PASSWORD") or None,
        timeout=float(env.get("PULSE_EP_MCP_TIMEOUT") or DEFAULT_TIMEOUT),
    )
