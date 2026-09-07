# Configuration

`pulse-ep` follows the [twelve-factor](https://12factor.net/config) pattern:
service settings are environment variables, with a `.env` file
for convenience and a legacy `config.ini` fallback for backwards
compatibility with pre-open-source deployments.

The settings model is defined in
[`pulse_ep.core.config.Settings`][pulse_ep.core.config.Settings] (a
[`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
class) and exposed through [`get_settings()`][pulse_ep.core.config.get_settings].

## Resolution order

Values are resolved in this order; the first match wins.

1. **Process environment** — `PULSE_EP_*` variables exported in your shell
   or set by `docker run -e`.
2. **`.env` file** — loaded automatically from the current working directory.
   Override the path with `PULSE_EP_ENV_FILE=path/to/file.env`.
3. **Legacy `config.ini`** — read if present at `./config.ini` (override
   with `PULSE_EP_CONFIG=...`). Used for backwards compatibility with the
   pre-open-source deployment.
4. **Field defaults** — defined on
   [`Settings`][pulse_ep.core.config.Settings].

!!! tip "Tip — single source of truth across local & Docker"

    Both local services and Docker Compose read `.env`. Compose overrides the
    in-container host, port, database URL and storage paths; it builds the
    database URL from `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`.
    The separate MCP process requires its own environment configuration.

## Quick start

```bash
cp .env.example .env
```

Edit `.env`, then follow the [quickstart](quickstart.md) to initialise the
database and accounts before starting the service.

## Service settings

The full reference table — what each variable does, its default, validation
rules, and which subsystem cares about it. MCP-process connection and download
settings are listed separately in the [MCP guide](../guides/mcp.md).

| Variable                          | Default               | Type                | Where it is used                                                  |
| --------------------------------- | --------------------- | ------------------- | ----------------------------------------------------------------- |
| `PULSE_EP_DATABASE_URL`           | _none_                | SQLAlchemy URL      | Full connection string. If set, takes precedence over components. |
| `PULSE_EP_DATABASE_USER`          | _none_                | string              | Component-mode: PostgreSQL user.                                  |
| `PULSE_EP_DATABASE_PASSWORD`      | _none_                | `SecretStr`         | Component-mode: PostgreSQL password (redacted in `repr()`).       |
| `PULSE_EP_DATABASE_HOST`          | _none_                | string              | Component-mode: host.                                             |
| `PULSE_EP_DATABASE_PORT`          | `5432`                | int                 | Component-mode: port.                                             |
| `PULSE_EP_DATABASE_NAME`          | _none_                | string              | Component-mode: database name.                                    |
| `PULSE_EP_HOST`                   | `127.0.0.1`           | string              | Bind address for `pulse-ep-server`; the Docker gunicorn command also reads it.                    |
| `PULSE_EP_PORT`                   | `5000`                | int                 | HTTP port.                                                        |
| `PULSE_EP_DEBUG`                  | `false`               | bool                | Flask debug mode. **Never enable in production.**                 |
| `PULSE_EP_JWT_SECRET_KEY`         | _dev placeholder_     | `SecretStr`         | Signs JWT access tokens. **Required for any non-dev deployment.** |
| `PULSE_EP_BCRYPT_LOG_ROUNDS`      | `12`                  | int (4–20)          | bcrypt cost factor. Higher values increase password-hashing work.        |
| `PULSE_EP_CORS_ORIGINS`           | `*`                   | comma-separated     | Allowed CORS origins.                                             |
| `PULSE_EP_REPORTS_DIR`            | `reports`             | path                | Directory for generated Excel / KML reports.                      |
| `PULSE_EP_DROP_DIR` | `drop` | path | Directory scanned by the import queue on request. |
| `PULSE_EP_WAVEFORM_STORE_DIR` | empty | path | Parquet store used by queue import and authenticated downloads. |
| `PULSE_EP_MCP_ENABLED` | `false` | bool | Explicit opt-in for identified MCP requests; also set in the MCP process. |
| `PULSE_EP_ENV_FILE`               | `.env`                | path                | Where to look for the `.env` file.                                |
| `PULSE_EP_CONFIG`                 | `config.ini`          | path                | Legacy INI-style config fallback path.                            |

### Database

You can supply the database either as a full URL (Option A) or as
components (Option B). Option B is handy when the password lives in a
separate secret store and the rest is plaintext config.

=== "Option A — full URL"

    ```bash
    PULSE_EP_DATABASE_URL=postgresql://pulse:pulse@localhost:5432/pulse
    ```

=== "Option B — components"

    ```bash
    PULSE_EP_DATABASE_USER=pulse
    PULSE_EP_DATABASE_PASSWORD=pulse
    PULSE_EP_DATABASE_HOST=localhost
    PULSE_EP_DATABASE_PORT=5432
    PULSE_EP_DATABASE_NAME=pulse
    ```

When both A and B are set, A wins.

### Security

```bash
PULSE_EP_JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
PULSE_EP_BCRYPT_LOG_ROUNDS=12
PULSE_EP_CORS_ORIGINS=https://app.example.com,https://staging.example.com
```

!!! warning "About the JWT secret"

    If `PULSE_EP_JWT_SECRET_KEY` is unset, the server falls back to an
    obviously insecure dev placeholder **and** emits a `RuntimeWarning`
    at import time. This keeps tests and import smoke checks green, but
    it must never be relied on in production. Any non-test deployment
    must set this variable.

### HTTP server

```bash
PULSE_EP_HOST=0.0.0.0
PULSE_EP_PORT=5000
PULSE_EP_DEBUG=0
```

Boolean values accept `1/0`, `true/false`, `yes/no`, `on/off` —
case-insensitively. CORS origins are comma-separated; whitespace around
commas is stripped.

## Reading settings from Python

```python
from pulse_ep.core.config import get_settings, reset_settings

s = get_settings()
print(s.host, s.port, s.bcrypt_log_rounds)
print("Database configured:", s.resolved_database_url is not None)
print("Explicit JWT secret configured:", s.jwt_secret_key is not None)
```

[`get_settings`][pulse_ep.core.config.get_settings] returns a cached
singleton. In tests, mutate `os.environ` then call
[`reset_settings()`][pulse_ep.core.config.reset_settings] to force a
fresh read.

## Common recipes

??? example "Production server behind a reverse proxy"

    ```bash
    PULSE_EP_HOST=127.0.0.1
    PULSE_EP_PORT=5000
    PULSE_EP_DEBUG=0
    PULSE_EP_DATABASE_URL=postgresql://pulse:…@db.internal:5432/pulse
    PULSE_EP_JWT_SECRET_KEY=…
    PULSE_EP_CORS_ORIGINS=https://app.example.com
    PULSE_EP_BCRYPT_LOG_ROUNDS=12
    ```

    Run behind nginx / Caddy / Traefik on the same host. The reverse proxy
    terminates TLS and forwards to `127.0.0.1:5000`.

??? example "Local development against a Docker Postgres"

    ```bash
    PULSE_EP_DATABASE_URL=postgresql://pulse:pulse@localhost:5432/pulse
    PULSE_EP_JWT_SECRET_KEY=dev-only-not-secret
    PULSE_EP_DEBUG=1
    ```

    Bring up the database with `docker compose up -d`, then run the
    server in-process with `pulse-ep-server`.

??? example "Migrating from a legacy pulse-ultimate `config.ini`"

    You do not need to touch your existing `config.ini` — pulse-ep reads
    it as the lowest-priority source. The recommended migration is:

    1. Run pulse-ep against your existing `config.ini` to confirm
       behaviour is unchanged.
    2. Generate an equivalent `.env`:

       ```bash
       PULSE_EP_DATABASE_URL=postgresql://${user}:${password}@${host}:${port}/${dbname}
       PULSE_EP_JWT_SECRET_KEY=${jwt_secret_key}
       ```
    3. Retire the legacy configuration after verifying the equivalent settings.

## See also

- [REST API reference](../reference/rest-api.md) — which endpoints are
  protected by `PULSE_EP_JWT_SECRET_KEY`.
- [Docker deployment](../guides/docker-deployment.md) — how the same
  variables flow into `docker compose`.
- [`pulse_ep.core.config`][pulse_ep.core.config] — the Python module
  that owns the settings model.
