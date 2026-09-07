# Docker deployment

The supplied Compose file starts PostgreSQL 16, with optional server and
pgAdmin services. Docker Compose 2.24 or newer is required.

## First-time setup

```bash
git clone https://github.com/swillert/pulse-ep.git
cd pulse-ep
cp .env.example .env
# Set a generated PULSE_EP_JWT_SECRET_KEY and your database credentials.
docker compose --profile server up -d --build
docker compose exec server pulse-ep-migrate
docker compose exec server pulse-ep-populate-colormaps
docker compose exec server pulse-ep-create-user --username admin --role admin
```

Open `http://localhost:5000`. The image installs the server, reporting and
7-Zip extras and runs gunicorn as a non-root user. It does not include an
MCP host; MCP clients connect separately to the REST service.

## Profiles and configuration

| Profile | Services |
| --- | --- |
| none | PostgreSQL |
| `server` | PostgreSQL and API/viewer |
| `admin` | PostgreSQL and pgAdmin |

Combine `--profile server --profile admin` to start all three. Set
`POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` in `.env` for the database;
Compose constructs the server's database URL from those values. The defaults
are for local development. Host ports are `POSTGRES_PORT` (5432),
`PULSE_EP_HOST_PORT` (5000) and `PGADMIN_PORT` (8080).

Compose overrides the service's internal bind address and file-store paths.
The same `.env` is useful for host configuration, but `localhost` on the host
and `postgres` inside the container network are different database addresses.
Use the documented service environment block for container-specific values.

## Persistent storage

| Named volume | Content |
| --- | --- |
| `pulse-ep-pgdata` | PostgreSQL data |
| `pulse-ep-reports` | Generated Excel files |
| `pulse-ep-waveforms` | Parquet signal files |
| `pulse-ep-drop` | Export bundles for import review |
| `pulse-ep-pgadmin` | Optional pgAdmin configuration |

The service's signal store is `/var/lib/pulse-ep/waveforms` and its drop
directory is `/var/lib/pulse-ep/drop`. These paths remain available across
container replacement. Back up the Parquet volume together with the database;
reference rows alone cannot reconstruct the signals.

## Import an export

```bash
docker compose cp /local/path/study.zip server:/tmp/study.zip
docker compose exec server pulse-ep-import-carto -i /tmp/study.zip --dry-run
docker compose exec server pulse-ep-import-carto -i /tmp/study.zip \
  --waveforms --store-dir /var/lib/pulse-ep/waveforms
```

Omit waveform options for geometry and measurements only. Substitute
`pulse-ep-import-ensite` for the other vendor. Alternatively, place completed
bundles in the mounted drop directory and use `/import` to scan and review.

## Upgrade

After checking out the intended release and backing up the data:

```bash
docker compose --profile server stop server
docker compose --profile server build server
docker compose --profile server run --rm --no-deps server pulse-ep-migrate
docker compose --profile server up -d server
docker compose exec server pulse-ep-populate-colormaps
```

The migration command runs with the existing PostgreSQL service available.
Table creation at server startup does not replace migrations for existing
columns. Existing named volumes are retained.

## Operations

Follow logs with `docker compose logs -f server`. Back up PostgreSQL with:

```bash
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > pulse-ep.sql
```

`docker compose --profile server --profile admin down` stops the stack.
Adding `-v` **deletes its named volumes**, including database, reports and
signals. Use that only for an intentional reset.

## Institutional deployment

Use a generated JWT secret, non-default database credentials, restricted
network access and TLS termination at a reverse proxy. The API permits
standard-user self-registration and uses database-wide roles; the proxy or
network must enforce the institution's access policy. Keep PostgreSQL and
pgAdmin off public interfaces. MCP is disabled by default; review institutional
rules before setting `PULSE_EP_MCP_ENABLED=1` and restarting the service.

If a service fails to start, inspect its logs and PostgreSQL health, confirm
the database URL and apply outstanding migrations. Ensure mounted directories
are writable by the container user (UID 10001).
