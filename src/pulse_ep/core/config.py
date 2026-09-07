"""Typed application configuration for pulse-ep.

Settings are resolved in this order of priority (highest first):

1. Environment variables, prefixed with ``PULSE_EP_`` (e.g.
   ``PULSE_EP_DATABASE_URL``, ``PULSE_EP_HOST``, ``PULSE_EP_JWT_SECRET_KEY``).
2. A ``.env`` file in the working directory — overridable via
   ``PULSE_EP_ENV_FILE``.
3. Legacy ``config.ini`` (overridable via ``PULSE_EP_CONFIG``) — backwards
   compatibility with the pre-open-source pulse-ultimate layout.
4. Field defaults defined on :class:`Settings`.

Use :func:`get_settings` to obtain a cached singleton; call
:func:`reset_settings` in tests when you mutate environment variables
between cases.

Example
-------
::

    # .env
    PULSE_EP_DATABASE_URL=postgresql://pulse:pulse@localhost:5432/pulse
    PULSE_EP_JWT_SECRET_KEY=change-me-in-production
    PULSE_EP_HOST=0.0.0.0
    PULSE_EP_PORT=5000

    >>> from pulse_ep.core.config import get_settings
    >>> s = get_settings()
    >>> s.host, s.port
    ('0.0.0.0', 5000)
"""

from __future__ import annotations

import configparser
import os
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _env_file_path() -> str:
    """Resolve the .env file path, honoring ``PULSE_EP_ENV_FILE``."""
    return os.environ.get("PULSE_EP_ENV_FILE", ".env")


class Settings(BaseSettings):
    """Validated application settings for pulse-ep.

    Field names use snake_case; corresponding environment variables are
    upper-cased and prefixed with ``PULSE_EP_`` (e.g. ``database_url``
    → ``PULSE_EP_DATABASE_URL``).
    """

    model_config = SettingsConfigDict(
        env_prefix="PULSE_EP_",
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database -------------------------------------------------------
    database_url: str | None = Field(
        default=None,
        description=(
            "Full SQLAlchemy URL. If set, takes precedence over the "
            "user/password/host/port/name components below."
        ),
    )
    database_user: str | None = None
    database_password: SecretStr | None = None
    database_host: str | None = None
    database_port: int = 5432
    database_name: str | None = None

    # --- HTTP server ----------------------------------------------------
    host: str = Field(default="127.0.0.1", description="Bind address for Flask/gunicorn.")
    port: int = Field(default=5000, description="TCP port.")
    debug: bool = Field(default=False, description="Enable Flask debug mode (development only).")

    # --- Security -------------------------------------------------------
    jwt_secret_key: SecretStr | None = Field(
        default=None,
        description=(
            "Symmetric key used to sign JWT access tokens. Required for "
            "production; if absent the server falls back to a clearly "
            "insecure dev placeholder and logs a warning."
        ),
    )
    bcrypt_log_rounds: int = Field(
        default=12,
        ge=4,
        le=20,
        description="bcrypt cost factor (log2 rounds). 12 ≈ 250 ms per hash on a 2024 laptop.",
    )
    # ``NoDecode`` disables pydantic-settings' default JSON parsing for
    # complex fields, so our ``_split_cors`` validator below can accept
    # plain comma-separated strings instead of requiring JSON arrays.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        description=(
            "Allowed CORS origins. Comma-separated string is accepted "
            "(e.g. ``https://app.example.com,https://staging.example.com``)."
        ),
    )

    # --- Application ----------------------------------------------------
    reports_dir: str = Field(
        default="reports",
        description="Filesystem directory used by /save_report and /reports/<id>/generate.",
    )
    drop_dir: str = Field(
        default="drop",
        description="Drop directory the import watcher scans for new export bundles.",
    )
    mcp_enabled: bool = Field(
        default=False,
        description=(
            "Whether this deployment serves the MCP server (pulse-ep-mcp). "
            "Off unless set: AI access is opted into, because serving it means "
            "study data leaves this deployment for a language model. While it "
            "is off, requests that identify themselves as MCP are refused with "
            "403, and pulse-ep-mcp refuses to start against this server. The "
            "identification is honest self-declaration, so this stops a "
            "forgotten or misconfigured MCP, not a person with valid "
            "credentials and curl — for that, disable the account."
        ),
    )
    waveform_store_dir: str = Field(
        default="",
        description=(
            "Root directory for Parquet waveform storage. Empty disables waveform "
            "import via the queue; the CLI takes --store-dir instead."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        """Accept ``"a,b,c"`` strings from .env files."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return v

    # ------------------------------------------------------------------
    # Computed views
    # ------------------------------------------------------------------
    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def resolved_database_url(self) -> str | None:
        """The effective DB URL, with the resolution order documented above.

        1. ``database_url`` (env / .env), if set.
        2. Components (user/password/host/port/name) — useful for
           operators who prefer setting only the secret in a separate
           store and keeping the rest in plaintext config.
        3. Legacy ``config.ini`` ``[database]`` section.
        """
        if self.database_url:
            return self.database_url
        if all(
            v is not None
            for v in (
                self.database_user,
                self.database_password,
                self.database_host,
                self.database_name,
            )
        ):
            assert self.database_password is not None  # narrowed by the check above
            pw = self.database_password.get_secret_value()
            return (
                f"postgresql://{self.database_user}:{pw}@"
                f"{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return _resolve_legacy_database_url()

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def resolved_jwt_secret_key(self) -> str | None:
        """The effective JWT secret. Falls back to legacy config.ini."""
        if self.jwt_secret_key is not None:
            return self.jwt_secret_key.get_secret_value()
        return _resolve_legacy_jwt_secret()


# ----------------------------------------------------------------------
# Legacy config.ini support (pulse-ultimate compatibility)
# ----------------------------------------------------------------------
def _read_legacy_config() -> configparser.ConfigParser | None:
    path = os.environ.get("PULSE_EP_CONFIG", "config.ini")
    if not os.path.exists(path):
        return None
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def _resolve_legacy_database_url() -> str | None:
    cfg = _read_legacy_config()
    if cfg is None or "database" not in cfg:
        return None
    db = cfg["database"]
    required = ("user", "password", "host", "port", "dbname")
    if not all(k in db for k in required):
        return None
    return f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['dbname']}"


def _resolve_legacy_jwt_secret() -> str | None:
    cfg = _read_legacy_config()
    if cfg is None or "jwt" not in cfg:
        return None
    return cfg["jwt"].get("secret_key")


# ----------------------------------------------------------------------
# Public access
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The cache makes settings cheap to access from request handlers and
    keeps the legacy config.ini read at module-level out of hot paths.
    """
    return Settings()


def reset_settings() -> None:
    """Clear the :func:`get_settings` cache.

    Call this in tests after mutating environment variables so the next
    :func:`get_settings` call picks up the new environment.
    """
    get_settings.cache_clear()
