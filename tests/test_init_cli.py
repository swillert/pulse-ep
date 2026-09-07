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
    # and the secret it did not have is offered from the new values
    assert effective["PULSE_EP_JWT_SECRET_KEY"] == "generated-secret"
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
