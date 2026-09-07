"""Regression checks for executable release instructions."""

import json
from types import SimpleNamespace

import pytest

from pulse_ep.cli import check_mesh, import_ensite


def test_mesh_help_needs_no_credentials_or_service(monkeypatch):
    monkeypatch.setattr(
        check_mesh.requests, "post", lambda *a, **kw: pytest.fail("HTTP during --help")
    )
    with pytest.raises(SystemExit) as exc:
        check_mesh.main(["--help"])
    assert exc.value.code == 0


def test_mesh_diagnostic_uses_raw_data_and_keeps_token_out_of_output(monkeypatch, capsys):
    monkeypatch.setenv("PULSE_EP_USERNAME", "diagnostic")
    monkeypatch.setenv("PULSE_EP_PASSWORD", "private-password")
    token = "private-access-token"
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"access_token": token})

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "mesh_data": {
                    "vertices": [[0, 0, 0]],
                    "faces": [],
                    "scalar_fields": {"voltage_bipolar": {}},
                },
                "point_data": {"coordinates": []},
                "scalar_name": "voltage_bipolar",
            },
        )

    monkeypatch.setattr(check_mesh.requests, "post", post)
    monkeypatch.setattr(check_mesh.requests, "get", get)
    assert check_mesh.main(["--map-id", "12", "--base-url", "http://example.test"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["vertices"] == 1
    assert token not in output and "private-password" not in output
    assert calls[1][1]["params"]["representation"] == "raw"
    assert calls[1][1]["params"]["scalar_name"] is None
    assert calls[1][1]["headers"]["Authorization"] == f"Bearer {token}"


def test_ensite_cli_rejects_missing_signal_store_before_import(monkeypatch):
    monkeypatch.setattr(
        import_ensite, "source_for", lambda *a: pytest.fail("read before validation")
    )
    with pytest.raises(SystemExit) as exc:
        import_ensite.main(["-i", "unused.zip", "--waveforms"])
    assert exc.value.code == 2
    with pytest.raises(ValueError, match="store-dir"):
        import_ensite.import_ensite("unused.zip", waveforms=True)


def test_migration_config_preserves_percent_encoded_passwords():
    from pulse_ep.cli.migrate import _alembic_config

    url = "postgresql://example:p%40ss%25word@localhost/example"
    assert _alembic_config(url).get_main_option("sqlalchemy.url") == url
