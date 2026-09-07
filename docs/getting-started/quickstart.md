# Quickstart

Three ways to see pulse-ep doing useful work, from quickest to most realistic.

## 1. Synthetic walkthrough (no DB needed)

```bash
pulse-ep-demo
```

What this does:

1. Builds an atrium-like ellipsoid with half-axes 25 / 25 / 35 mm, from a
   sphere at `--resolution 24` — 530 vertices, 1056 triangles.
2. Paints a Gaussian pace-mapping score field onto it: σ = 6 mm, with 2 %
   relative noise.
3. Wraps mesh and field as an `EPMap` — the same domain object the CARTO and
   EnSiteX importers produce.
4. Computes the total surface area and the area falling into each score
   interval, and prints the result.

**No database is involved** — not PostgreSQL, and nothing embedded either.
Nothing is written and nothing is read back; the demo exercises the array-only
public API. If `pulse-ep-demo` finishes cleanly, your installation is healthy;
what it does *not* prove is that a database, the server or an import works.
Step 2 and 3 below cover those.

Add `--show` for an interactive 3D view of the result.

??? note "Sample output"

    ```
    pulse-ep demo — synthetic atrium with a Gaussian pace-mapping field
    ------------------------------------------------------------------------
    mesh:           530 vertices, 1056 triangles
    score field:    σ = 6.0 mm, origin vertex = 0
                    min/median/max = 0.0 / 0.7 / 100.0 %
    surface area:   99.44 cm² (total)
    EPMap:          name='synthetic_demo', study='pulse-ep demo'

    Area by score interval (mean of triangle vertices):
      interval (%)     area (cm²)    % of total
      [   0,   20)          96.11         96.7 %
      [  20,   40)           1.14          1.2 %
      [  40,   60)           0.72          0.7 %
      [  60,   80)           1.10          1.1 %
      [  80,   90)           0.09          0.1 %
      [  90,   95)           0.27          0.3 %
      [  95,  100)           0.00          0.0 %
      [ 100,  101)           0.00          0.0 %
    ```


## The short way

```bash
pip install -e ".[all]"
docker compose up -d          # PostgreSQL
pulse-ep-init                 # asks what it cannot work out, does the rest
pulse-ep-server
```

`pulse-ep-init` writes `.env` with a generated JWT secret, creates the
waveform and drop directories, applies the migrations, seeds the colormaps
(forgetting this is why a viewer shows no colours), creates an
administrator, and — if you want one — a **read-only** account for the MCP
server, printing the client configuration to paste. It is idempotent: run it
again after an upgrade.

`--non-interactive` asks nothing and takes flags and defaults, for a
scripted install. The rest of this page is the same steps by hand.

## 2. A real study, local Python install

This is the workflow for researchers running pulse-ep on their own laptop
against an existing PostgreSQL database. It is the same for both supported
vendors — only the import command differs.

### 2.1. Start Postgres

```bash
docker compose up -d
```

The default profile of [`compose.yaml`](../guides/docker-deployment.md)
starts a healthchecked PostgreSQL 16 with persistent volume `pulse-ep-pgdata`.

### 2.2. Configure the connection

```bash
cp .env.example .env
```

Edit `.env`:

```bash
PULSE_EP_DATABASE_URL=postgresql://pulse:pulse@localhost:5432/pulse
PULSE_EP_JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

See [Configuration](configuration.md) for the full list of variables.

### 2.3. Create the schema

```bash
pulse-ep-migrate
```

The migrations ship with the package, so this works from anywhere — a
source checkout or a plain `pip install`. It reads the same
`PULSE_EP_DATABASE_URL`, needs no configuration of its own, creates every
table on an empty database and applies only the outstanding ones on an
existing database. `pulse-ep-migrate --current` reports where a database
stands.

From a source checkout, `alembic upgrade head` does the same thing through
`alembic.ini`. (The server also calls `init_db()` at startup, which creates
any missing tables — but migrations are what keep an *existing* database in
step with a new release.)

### 2.4. Import a study

Both importers accept an export **folder or ZIP**, and both can show you
what they would do before writing anything:

=== "CARTO 3"

    ```bash
    pulse-ep-import-carto -i /path/to/carto-export-dir
    ```

    Takes a **directory** — unpack an archived export first. It discovers the
    study XML manifests, parses them with the `.mesh` files, and populates the
    database. A 60-map study with full point clouds takes about 60–90 seconds
    on a modern laptop.

    See the [CARTO import guide](../guides/carto-import.md).

=== "EnSiteX"

    ```bash
    # print the plan — maps, scalar fields, point counts, issues — and stop
    pulse-ep-import-ensite -i /path/to/ensite-export.zip --dry-run

    # then import for real
    pulse-ep-import-ensite -i /path/to/ensite-export.zip

    # optionally include the signal data (opt-in; it can dwarf the export)
    pulse-ep-import-ensite -i /path/to/export.zip \
        --waveforms --store-dir /var/pulse/waveforms
    ```

    Imports are idempotent by the export's study GUID — re-running skips a
    study that is already present unless you pass `--clear`.

    See the [EnSiteX import guide](../guides/ensite-import.md).

!!! tip "Run `--dry-run` first on an unfamiliar export"

    The plan tells you which maps were detected, which quantities each
    carries, how many measurement points came with them, and anything the
    importer found questionable — before a single row is written.

### 2.5. Seed defaults and create a user

```bash
pulse-ep-populate-colormaps
pulse-ep-create-user --username admin --role admin
```

The colormap seeder loads the bundled clinical colormaps; without them
the viewer falls back to a plain blue-to-red linear ramp. The user
creator prompts for a password if `--password` is not given.

### 2.6. Launch the web app

```bash
pulse-ep-server
```

By default, the server binds to `http://127.0.0.1:5000`. Log in with the
admin credentials you just created and you should see your imported
studies in the dashboard.

## 3. Full Docker stack

For the closest-to-production setup — server, database and (optionally)
pgAdmin in containers, with no Python on the host:

```bash
cp .env.example .env
# edit PULSE_EP_JWT_SECRET_KEY at minimum

docker compose --profile server up -d --build

docker compose exec server pulse-ep-create-user --username admin --role admin

docker compose --profile admin up -d        # optional, pgAdmin on :8080
```

The Docker stack uses the same `.env` file as the local install, so
configuration carries across. See the
[Docker deployment guide](../guides/docker-deployment.md) for the full
profile, volume and networking story.

## Testing your install

### Without a database or a server

The repository ships two synthetic vendor exports — one CARTO 3, one
EnSite X — so the import path can be checked without patient data:

```bash
examples/verify.sh
```

It decodes both and prints mesh, scalar fields, measurement points and
surface area for each. Both exports carry the *same* surface, so the two
readers can be compared against one another.

!!! note "What this establishes"

    The file formats are read completely. It does **not** establish that a
    field means what we call it — that the column named `voltage_bipolar`
    really holds the bipolar voltage can only be shown against real vendor
    exports, which are patient data and are not part of this repository.
    See `tests/fixtures/synthetic/README.md`.

### With the server running

Once the server is up, this curl one-liner exercises the full
authentication and data flow:

```bash
export PULSE_EP_BASE_URL=http://127.0.0.1:5000
export PULSE_EP_USERNAME=admin
export PULSE_EP_PASSWORD=…

TOKEN=$(curl -s -X POST "$PULSE_EP_BASE_URL/login_user" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$PULSE_EP_USERNAME\",\"password\":\"$PULSE_EP_PASSWORD\"}" \
    | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
curl -s "$PULSE_EP_BASE_URL/list_studies" \
    -H "Authorization: Bearer $TOKEN" \
    | python -m json.tool
```

If that prints a JSON array of studies, your full pipeline is working
end to end.

## Where to go next

- **[Configuration](configuration.md)** — all `PULSE_EP_*` settings, the
  resolution order, and how to use a `.env` file.
- **[CARTO import guide](../guides/carto-import.md)** — what a CARTO export
  contains, how to tag pace-maps, batch imports from a study CSV.
- **[Web viewer guide](../guides/web-viewer.md)** — tour of the bundled
  Three.js viewer with screenshots.
- **[REST API reference](../reference/rest-api.md)** — every endpoint with
  request/response shapes.
- **[Examples](../examples/index.md)** — cross-language client code in R,
  MATLAB, ParaView and Jupyter.
