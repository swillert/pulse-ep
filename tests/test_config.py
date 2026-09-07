"""Tests for :mod:`pulse_ep.core.config`.

These tests exercise the precedence rules and validators of the
:class:`Settings` model. They never touch a real database.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from pulse_ep.core.config import Settings, get_settings, reset_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Ensure each test starts with a fresh Settings cache."""
    reset_settings()
    yield
    reset_settings()


# --- Field defaults ---------------------------------------------------------
def test_defaults_when_no_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    # Wipe every PULSE_EP_* var inherited from the host
    for k in list(os.environ):
        if k.startswith("PULSE_EP_"):
            monkeypatch.delenv(k, raising=False)

    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 5000
    assert s.debug is False
    assert s.mcp_enabled is False
    assert s.database_url is None
    assert s.resolved_database_url is None
    assert s.resolved_jwt_secret_key is None
    assert s.cors_origins == ["*"]
    assert s.bcrypt_log_rounds == 12
    assert s.reports_dir == "reports"


# --- Env overrides ----------------------------------------------------------
def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_EP_HOST", "0.0.0.0")
    monkeypatch.setenv("PULSE_EP_PORT", "8080")
    monkeypatch.setenv("PULSE_EP_DEBUG", "true")
    monkeypatch.setenv("PULSE_EP_JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PULSE_EP_CORS_ORIGINS", "https://a.example,https://b.example")

    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8080
    assert s.debug is True
    assert s.resolved_jwt_secret_key == "test-secret"
    assert s.cors_origins == ["https://a.example", "https://b.example"]


# --- database_url precedence ------------------------------------------------
def test_database_url_takes_precedence_over_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_EP_DATABASE_URL", "postgresql://full/url")
    monkeypatch.setenv("PULSE_EP_DATABASE_USER", "u")
    monkeypatch.setenv("PULSE_EP_DATABASE_PASSWORD", "p")
    monkeypatch.setenv("PULSE_EP_DATABASE_HOST", "h")
    monkeypatch.setenv("PULSE_EP_DATABASE_NAME", "db")

    s = Settings()
    assert s.resolved_database_url == "postgresql://full/url"


def test_database_components_compose_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PULSE_EP_DATABASE_URL", raising=False)
    monkeypatch.setenv("PULSE_EP_DATABASE_USER", "pulse")
    monkeypatch.setenv("PULSE_EP_DATABASE_PASSWORD", "secret")
    monkeypatch.setenv("PULSE_EP_DATABASE_HOST", "db.example")
    monkeypatch.setenv("PULSE_EP_DATABASE_PORT", "5433")
    monkeypatch.setenv("PULSE_EP_DATABASE_NAME", "pulse")

    s = Settings()
    assert s.resolved_database_url == "postgresql://pulse:secret@db.example:5433/pulse"


def test_password_is_redacted_in_repr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_EP_DATABASE_PASSWORD", "super-secret-pw")
    monkeypatch.setenv("PULSE_EP_JWT_SECRET_KEY", "super-secret-jwt")

    s = Settings()
    rep = repr(s)
    assert "super-secret-pw" not in rep
    assert "super-secret-jwt" not in rep
    assert "**********" in rep


# --- Legacy config.ini fallback --------------------------------------------
def test_legacy_config_ini_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If no env-based DB config is present, fall back to config.ini."""
    for k in list(os.environ):
        if k.startswith("PULSE_EP_"):
            monkeypatch.delenv(k, raising=False)
    ini = tmp_path / "config.ini"
    ini.write_text(
        textwrap.dedent(
            """
            [database]
            user = legacy
            password = legacypw
            host = legacyhost
            port = 5432
            dbname = legacydb

            [jwt]
            secret_key = legacy-jwt-secret
            """
        ).strip()
    )
    monkeypatch.setenv("PULSE_EP_CONFIG", str(ini))

    s = Settings()
    assert s.resolved_database_url == "postgresql://legacy:legacypw@legacyhost:5432/legacydb"
    assert s.resolved_jwt_secret_key == "legacy-jwt-secret"


# --- .env file --------------------------------------------------------------
def test_dotenv_file_is_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for k in list(os.environ):
        if k.startswith("PULSE_EP_"):
            monkeypatch.delenv(k, raising=False)
    env_file = tmp_path / "custom.env"
    env_file.write_text("PULSE_EP_HOST=10.0.0.5\nPULSE_EP_PORT=9000\n")
    monkeypatch.setenv("PULSE_EP_ENV_FILE", str(env_file))

    s = Settings(_env_file=str(env_file))
    assert s.host == "10.0.0.5"
    assert s.port == 9000


# --- Caching behaviour ------------------------------------------------------
def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_EP_HOST", "10.0.0.1")
    s1 = get_settings()
    monkeypatch.setenv("PULSE_EP_HOST", "10.0.0.2")
    s2 = get_settings()
    assert s1 is s2  # cached
    assert s2.host == "10.0.0.1"

    reset_settings()
    s3 = get_settings()
    assert s3.host == "10.0.0.2"


# --- Validation -------------------------------------------------------------
def test_bcrypt_log_rounds_out_of_range_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_EP_BCRYPT_LOG_ROUNDS", "30")
    with pytest.raises(ValueError):
        Settings()
