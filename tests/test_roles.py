"""The role claim has to mean something.

It was minted at login and never read again: the four endpoints the REST
reference calls "admin only" were not, the read-only account the MCP guide
recommends could set attributes and delete colormaps, and `/register_user`
had no authentication at all — anyone who could reach the server could ask
for `role: admin` and get it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("flask", reason="server extra: pip install 'pulse-ep[server]'")

from flask_jwt_extended import create_access_token  # noqa: E402

from pulse_ep.server.roles import ADMIN, READONLY, ROLES, USER  # noqa: E402


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv("PULSE_EP_JWT_SECRET_KEY", "test-only")
    from pulse_ep.server import app as app_module

    # Exceptions must become responses, not propagate: a read endpoint reached
    # without a database is a 500, and "not 403" is exactly what these tests
    # need to distinguish "the guard let it through" from "the guard refused".
    app_module.app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    return app_module.app


def _auth(app, role):
    with app.app_context():
        token = create_access_token(identity="someone", additional_claims={"role": role})
    return {"Authorization": f"Bearer {token}"}


ADMIN_ONLY = [
    ("post", "/epmaps/set_attributes", {"map_ids": [1], "attribute_values": {"pacemap": True}}),
    ("post", "/colormaps", {"name": "x", "colors": ["#000000"], "intervals": [0]}),
    ("put", "/colormaps/1", {"name": "x", "colors": ["#000000"], "intervals": [0]}),
    ("delete", "/colormaps/1", None),
]

WRITES = [
    ("post", "/save_report", {"report_name": "r", "map_ids": [1]}),
    ("post", "/reports/1/generate", {}),
    ("delete", "/reports/1", None),
    ("post", "/api/import-jobs/scan", {}),
    ("post", "/api/import-jobs", {"path": "/tmp/x"}),
    ("patch", "/api/import-jobs/1/plan", {"plan": {}}),
]


def _call(client, method, path, body, headers):
    send = getattr(client, method)
    return (
        send(path, json=body, headers=headers) if body is not None else send(path, headers=headers)
    )


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY)
def test_admin_only_endpoints_refuse_an_ordinary_user(http, method, path, body):
    with http.test_client() as client:
        response = _call(client, method, path, body, _auth(http, USER))
    assert response.status_code == 403
    assert response.get_json()["required"] == [ADMIN]


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY + WRITES)
def test_nothing_that_writes_accepts_a_read_only_account(http, method, path, body):
    """What makes "give the MCP a read-only account" true rather than a hope."""
    with http.test_client() as client:
        response = _call(client, method, path, body, _auth(http, READONLY))
    assert response.status_code == 403
    assert response.get_json()["role"] == READONLY


@pytest.mark.parametrize(
    "path",
    [
        "/list_studies",
        "/epmaps/1/scalars",
        "/epmaps/1/points",
        "/epmaps/1/waveforms",
        "/epmaps/distinct_attributes",
        "/api/import-jobs",
    ],
)
def test_a_read_only_account_may_read(http, path):
    """Past the guard, into ordinary handling — not a 403."""
    with http.test_client() as client:
        response = client.get(path, headers=_auth(http, READONLY))
    assert response.status_code != 403


def test_the_reads_that_arrive_as_posts_stay_open(http):
    """A filter, an area integration and a comparison compute; they store nothing."""
    for path, body in (
        ("/epmaps/filter_by_attributes", {"filters": {}}),
        ("/epmaps/get_attributes", {"map_ids": [1]}),
        ("/get_epmaps", {"epmap_ids": [1]}),
        ("/calculate_areas_for_intervals", {"map_id": 1, "intervals": [[0, 1]]}),
        ("/api/compare", {"map_a_id": 1, "map_b_id": 2, "scalar_name": "voltage_bipolar"}),
    ):
        with http.test_client() as client:
            response = client.post(path, json=body, headers=_auth(http, READONLY))
        assert response.status_code != 403, path


def test_an_account_from_before_the_roles_keeps_what_it_could_do(http):
    """An upgrade must not lock existing users out — but must not promote them."""
    with http.test_client() as client:
        no_claim = client.post("/save_report", json={"report_name": "r"}, headers=_auth(http, None))
        assert no_claim.status_code != 403  # treated as an ordinary user
        promoted = client.post("/colormaps", json={"name": "x"}, headers=_auth(http, None))
        assert promoted.status_code == 403  # but not as an administrator


# --- open registration -------------------------------------------------------


def test_registration_cannot_mint_an_administrator(http):
    with http.test_client() as client:
        response = client.post(
            "/register_user", json={"username": "mallory", "password": "x", "role": ADMIN}
        )
    assert response.status_code == 403
    assert "administrator" in response.get_json()["msg"]


def test_an_administrator_may_name_the_role(http, monkeypatch):
    created = {}
    from pulse_ep.server import app as app_module

    class _Session:
        def add(self, user):
            created["role"] = user.role

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(app_module, "get_db_session", lambda: _Session())
    with http.test_client() as client:
        response = client.post(
            "/register_user",
            json={"username": "colleague", "password": "x", "role": READONLY},
            headers=_auth(http, ADMIN),
        )
    assert response.status_code == 201
    assert created["role"] == READONLY


def test_an_unknown_role_is_refused_by_name(http):
    with http.test_client() as client:
        response = client.post(
            "/register_user",
            json={"username": "x", "password": "y", "role": "root"},
            headers=_auth(http, ADMIN),
        )
    assert response.status_code == 400
    assert str(list(ROLES)) in response.get_json()["msg"]


@pytest.mark.parametrize("path", ["/login_user", "/register_user"])
@pytest.mark.parametrize(
    "body", [[], {"username": [], "password": "x"}, {"username": "u", "password": 12}, {}]
)
def test_invalid_login_and_registration_bodies_are_client_errors(http, path, body):
    with http.test_client() as client:
        response = client.post(path, json=body)
    assert response.status_code == 400
    assert response.is_json


def test_duplicate_username_is_a_client_error(http, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy.exc import IntegrityError

    from pulse_ep.server import app as app_module

    @contextmanager
    def duplicate_session():
        class Session:
            def add(self, user):
                pass

            def commit(self):
                raise IntegrityError("insert", {}, Exception("duplicate"))

        yield Session()

    monkeypatch.setattr(app_module, "get_db_session", duplicate_session)
    with http.test_client() as client:
        response = client.post("/register_user", json={"username": "existing", "password": "x"})
    assert response.status_code == 400
    assert "already exists" in response.get_json()["msg"]
