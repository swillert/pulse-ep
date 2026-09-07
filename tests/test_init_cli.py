"""Setting a deployment up without getting one of fifteen steps wrong.

The parts that can be tested without a database: what is asked, what is
written, and — the one that matters — that a re-run never hands out a
credential which does not work.
"""

from __future__ import annotations

import json
import stat

from pulse_ep.cli.init import Asker, _read_env, env_values, mcp_client_config, write_env


def _values():
    return {
        "PULSE_EP_DATABASE_URL": "postgresql://pulse:pulse@localhost:5432/pulse",
        "PULSE_EP_JWT_SECRET_KEY": "generated-secret",
        "PULSE_EP_WAVEFORM_STORE_DIR": "waveforms",
    }


def test_a_fresh_env_file_is_written_and_kept_private(tmp_path):
    """It holds the JWT secret, so it is not world-readable."""
    path = tmp_path / ".env"
    written, effective = write_env(path, _values(), Asker(interactive=False))

    assert written is True
    assert effective == _values()
    assert _read_env(path) == _values()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_an_existing_file_is_kept_and_its_settings_win(tmp_path):
    """Re-running must configure what will run, not what would have been written."""
    path = tmp_path / ".env"
    path.write_text("PULSE_EP_DATABASE_URL=postgresql://elsewhere/db\n# a comment\n")

    written, effective = write_env(path, _values(), Asker(interactive=False))

    assert written is False
    assert effective["PULSE_EP_DATABASE_URL"] == "postgresql://elsewhere/db"
    # The generated secret must survive into a separately started server.
    assert effective["PULSE_EP_JWT_SECRET_KEY"] == "generated-secret"
    assert _read_env(path)["PULSE_EP_JWT_SECRET_KEY"] == "generated-secret"
    assert path.read_text().startswith("PULSE_EP_DATABASE_URL=postgresql://elsewhere/db")


def test_nothing_is_asked_when_nobody_is_there_to_answer():
    ask = Asker(interactive=False)
    assert ask.text("PostgreSQL URL", "postgresql://default") == "postgresql://default"
    assert ask.yes("Serve MCP access?", default=True) is True
    assert ask.yes("Replace it?", default=False) is False
    generated = ask.secret("Password")
    assert len(generated) >= 20 and generated != ask.secret("Password")


def test_the_mcp_block_is_ready_to_paste():
    block = json.loads(mcp_client_config("http://host:5000", "mcp", "s3cret"))
    server = block["mcpServers"]["pulse-ep"]
    assert server["command"].endswith("pulse-ep-mcp")
    assert server["env"]["PULSE_EP_MCP_BASE_URL"] == "http://host:5000"
    assert server["env"]["PULSE_EP_MCP_USERNAME"] == "mcp"
    assert server["env"]["PULSE_EP_MCP_PASSWORD"] == "s3cret"
    from pulse_ep.mcp.server import is_enabled

    assert is_enabled(server["env"])


def test_the_secret_is_generated_and_never_the_placeholder():
    """Unset, the server runs on a development placeholder and warns about it."""
    from pulse_ep.server.app import _DEV_JWT_PLACEHOLDER

    first = env_values("postgresql://x/y", "waveforms", "drop", mcp_enabled=True)
    second = env_values("postgresql://x/y", "waveforms", "drop", mcp_enabled=True)

    secret = first["PULSE_EP_JWT_SECRET_KEY"]
    assert len(secret) >= 43  # token_urlsafe(48)
    assert secret != second["PULSE_EP_JWT_SECRET_KEY"]  # per installation
    assert secret != _DEV_JWT_PLACEHOLDER
    assert first["PULSE_EP_MCP_ENABLED"] == "1"
    assert env_values("u", "w", "d", mcp_enabled=False)["PULSE_EP_MCP_ENABLED"] == "0"


def test_env_quotes_are_parsed_and_preserved(tmp_path, monkeypatch):
    monkeypatch.delenv("PULSE_EP_JWT_SECRET_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("PULSE_EP_JWT_SECRET_KEY='existing # secret'\n")
    _, effective = write_env(path, _values(), Asker(interactive=False))
    assert effective["PULSE_EP_JWT_SECRET_KEY"] == "existing # secret"
    from pulse_ep.core.config import Settings

    assert Settings(_env_file=path).jwt_secret_key.get_secret_value() == "existing # secret"


def test_new_env_roundtrips_special_characters(tmp_path):
    path = tmp_path / "nested" / ".env"
    values = {**_values(), "PULSE_EP_JWT_SECRET_KEY": "literal # and ' quote"}
    write_env(path, values, Asker(interactive=False))
    assert _read_env(path) == values


def test_init_respects_environment_and_existing_mcp_opt_out(tmp_path, monkeypatch, capsys):
    from pulse_ep.cli import init

    env_file = tmp_path / ".env"
    env_file.write_text("PULSE_EP_DATABASE_URL='postgresql://file/db'\nPULSE_EP_MCP_ENABLED=0\n")
    process_env = {
        "PULSE_EP_DATABASE_URL": "postgresql://process/db",
        "PULSE_EP_JWT_SECRET_KEY": "process-secret",
    }
    monkeypatch.setattr(init.os, "environ", process_env)
    monkeypatch.chdir(tmp_path)
    checked = []
    monkeypatch.setattr(init, "check_database", lambda url: checked.append(url))
    monkeypatch.setattr(init, "migrate", lambda: None)
    monkeypatch.setattr(init, "seed_colormaps", lambda: None)
    accounts = []
    monkeypatch.setattr(
        init, "create_account", lambda user, password, role: accounts.append(role) or True
    )
    assert init.main(["--non-interactive", "--mcp", "--mcp-user", "reader"]) == 0
    assert checked == ["postgresql://process/db"]
    assert process_env["PULSE_EP_JWT_SECRET_KEY"] == "process-secret"
    assert process_env["PULSE_EP_MCP_ENABLED"] == "0"
    assert accounts == ["admin"]
    out = capsys.readouterr().out
    assert "MCP access is ON" not in out
    # …but the operator asked for it, so it must not vanish without a word.
    assert "you asked for MCP on" in out
    assert "PULSE_EP_MCP_ENABLED" in out
