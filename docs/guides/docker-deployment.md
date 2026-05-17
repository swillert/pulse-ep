# Docker deployment

The `compose.yaml` shipped with the repository spins up the full stack —
PostgreSQL, the pulse-ep REST API and 3D viewer, and (optionally) pgAdmin —
with one command per profile.

## Files involved

| File              | Purpose                                                       |
| ----------------- | ------------------------------------------------------------- |
| `compose.yaml`    | Three-service stack with `default`, `server` and `admin` profiles. |
| `Dockerfile`      | Two-stage build for the `server` service: slim runtime image, non-root user, gunicorn entrypoint. |
| `.dockerignore`   | Keeps the build context lean — excludes `.git`, caches, secrets. |
| `.env.example`    | Reference for every environment variable consumed by the stack. |

## Profiles

The stack uses Docker Compose profiles so you only pay for what you use:

| Profile     | Brings up                  | Use case                                      |
| ----------- | -------------------------- | --------------------------------------------- |
| _(default)_ | `postgres`                 | Database only — e.g. for local Python runs.   |
| `server`    | `postgres` + `server`      | Self-contained API + viewer + database.       |
| `admin`     | `postgres` + `pgadmin`     | Web UI for the database (port 8080).          |

Combine profiles to bring up multiple services together:

```bash
docker compose --profile server --profile admin up -d --build
```

## First-time setup

```bash
git clone https://gitlab.willert.net/sw/pulse-ep.git
cd pulse-ep

# 1. Configure
cp .env.example .env
# edit at minimum:
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   PULSE_EP_JWT_SECRET_KEY

# 2. Bring up the stack
docker compose --profile server up -d --build

# 3. Bootstrap an admin user
docker compose exec server pulse-ep-create-user --username admin --role admin

# 4. (optional) Bring up pgAdmin on http://localhost:8080
docker compose --profile admin up -d
```

The viewer is now at <http://localhost:5000>.

## What the services do

### `postgres`

- `postgres:16-alpine` with `--encoding=UTF-8 --locale=C` for faster startup.
- Persists data in a named volume `pulse-ep-pgdata`.
- Exposes port `5432` to the host (overridable via `POSTGRES_PORT`).
- Has a `pg_isready` healthcheck. Dependents wait for it.

### `server`

- Two-stage build from the local `Dockerfile`:
    1. Builder image: `python:3.12-slim` with `build-essential` and `libpq-dev`, installs all wheels into `/opt/venv`.
    2. Runtime image: `python:3.12-slim` with only the runtime libraries (`libgl1`, `libglib2.0-0`, `libpq5`, `libgomp1`), plus the venv copied across. Drops to a non-root `pulse` user (UID 10001).
- Entrypoint runs `init_db()` once on startup, then exec's gunicorn with 2 workers × 4 threads, binding to `${PULSE_EP_HOST}:${PULSE_EP_PORT}`.
- Persists generated reports in a named volume `pulse-ep-reports`.
- HTTP healthcheck against `/` every 15 s.

### `pgadmin`

- `dpage/pgadmin4:latest` for browser-based SQL access.
- Server mode disabled (no per-user login screen — appropriate for a dev box).
- Persists configuration in named volume `pulse-ep-pgadmin`.

## Environment variables

The Compose file reads its variables from `.env`, which **also** drives
the `pulse-ep-server` process directly (whether it runs in a container
or natively). The relevant subset:

| Variable                  | Purpose                                                                   |
| ------------------------- | ------------------------------------------------------------------------- |
| `POSTGRES_USER`           | Postgres user / pulse-ep DB user (Compose wires them together).           |
| `POSTGRES_PASSWORD`       | dito.                                                                     |
| `POSTGRES_DB`             | Database name.                                                            |
| `POSTGRES_PORT`           | Host-side port for Postgres (default `5432`).                             |
| `PULSE_EP_HOST_PORT`      | Host-side port mapped to the server's `5000` (default `5000`).            |
| `PULSE_EP_JWT_SECRET_KEY` | Required. Generated once with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `PULSE_EP_DATABASE_URL`   | Auto-built inside the server container from `POSTGRES_*`. Override only for non-default setups. |
| `PGADMIN_EMAIL`           | pgAdmin login (default `admin@example.com`).                              |
| `PGADMIN_PASSWORD`        | pgAdmin password.                                                         |
| `PGADMIN_PORT`            | Host-side port for pgAdmin (default `8080`).                              |

The full reference (every `PULSE_EP_*` variable, defaults, types) is in
the [Configuration page](../getting-started/configuration.md).

## Common operations

### Importing a CARTO study into the running stack

```bash
# Copy the export into the container, then run the importer in-place.
docker compose cp /local/path/study.zip server:/tmp/study.zip
docker compose exec server pulse-ep-import-carto /tmp/study.zip
```

Or mount the export folder into the server service in `compose.yaml`
and run the importer from the running container.

### Tailing server logs

```bash
docker compose logs -f server
```

### Database backups

```bash
docker compose exec -T postgres \
    pg_dump -U "${POSTGRES_USER:-pulse}" "${POSTGRES_DB:-pulse}" \
    > pulse-ep-$(date +%F).sql
```

### Updating to a new pulse-ep version

```bash
git pull
docker compose --profile server up -d --build server
```

Compose only rebuilds the `server` image; the database is untouched.

### Resetting everything (wipes the database!)

```bash
docker compose --profile server --profile admin down -v
```

The `-v` removes the named volumes (`pulse-ep-pgdata`, `pulse-ep-reports`,
`pulse-ep-pgadmin`). Use this only when you mean it.

## Production checklist

Before pointing real traffic at this stack, review:

- [ ] `PULSE_EP_JWT_SECRET_KEY` is a fresh random 48-byte token, not
      the dev placeholder.
- [ ] `POSTGRES_PASSWORD` is unique and stored in your secret manager.
- [ ] `PULSE_EP_DEBUG=0` (the default; never `1` in production).
- [ ] `PULSE_EP_CORS_ORIGINS` is **not** `*` — list only the domains
      that need to call the API.
- [ ] The Postgres port (`POSTGRES_PORT`) is **not** exposed on a
      public interface. For local-only access, drop the `ports` mapping
      in `compose.yaml` and rely on the container network.
- [ ] A reverse proxy (nginx, Caddy, Traefik) terminates TLS and
      forwards to `PULSE_EP_HOST_PORT`. The container does not handle
      TLS itself.
- [ ] Regular `pg_dump` backups are scheduled.
- [ ] If you bring up `pgadmin` in production, change
      `PGADMIN_DEFAULT_PASSWORD` and put it behind the reverse proxy
      with authentication.

## Troubleshooting

??? failure "`server` container restarts in a loop after `docker compose up`"

    Most likely the database is not yet healthy. The server's
    `depends_on: { condition: service_healthy }` should prevent this,
    but a slow first-time `initdb` can occasionally timeout. Check
    `docker compose logs postgres` and re-run `up -d` after a minute.

??? failure "`pg_isready: command not found` healthcheck failure"

    The Postgres image dropped `pg_isready` from the slim variant in
    some 16.x patch versions. Pin to `postgres:16.4-alpine` in
    `compose.yaml` until upstream resolves it.

??? failure "Cannot connect from the host with `psql` even though the container is up"

    Check that `POSTGRES_PORT` in `.env` matches the port you are
    dialling. If you bind Postgres to `127.0.0.1` only (a good idea
    for security), connections from other hosts fail by design.

## See also

- [Configuration](../getting-started/configuration.md) — every
  `PULSE_EP_*` variable in detail.
- [Quickstart §3](../getting-started/quickstart.md#3-full-docker-stack)
  — the minimum-viable Docker walkthrough.
- [Managing users](managing-users.md) — how to add users inside a
  running container.
