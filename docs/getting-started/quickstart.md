# Quickstart

Run these commands from an installed source checkout with its virtual
environment activated; see [Installation](installation.md).

## 1. Synthetic walkthrough (no DB needed)

```bash
pulse-ep-demo
```

This builds an ellipsoid with half-axes 25, 25 and 35 mm, a synthetic Gaussian
pace-mapping field and an `EPMap`. At the default resolution of 24 it contains
530 vertices and 1,056 triangles. The output reports mesh size, score range,
total area and whole-triangle areas by score interval. Add `--show` for an
interactive PyVista view. The demo neither imports a vendor export nor saves
a database record.

The repository also supplies paired vendor-format fixtures:

```bash
examples/verify.sh
```

This decodes the same generated surface from CARTO and EnSite X layouts.
It checks the input readers without patient data or PostgreSQL. See the
[fixture description](https://github.com/swillert/pulse-ep/blob/main/tests/fixtures/synthetic/README.md)
for the scope of this check.

## 2. A stored study and the web viewer

### Start and initialise PostgreSQL

```bash
docker compose up -d
pulse-ep-init
```

The initializer writes configuration, applies schema migrations, seeds
colormaps and creates an administrator. If you use an existing PostgreSQL
installation, supply its connection details instead. MCP stays disabled
unless explicitly enabled after institutional review.

### Import a study

Both vendor commands accept a directory or archive:

```bash
pulse-ep-import-carto -i /path/to/carto-export.zip --dry-run
pulse-ep-import-carto -i /path/to/carto-export.zip

pulse-ep-import-ensite -i /path/to/ensite-export.zip --dry-run
pulse-ep-import-ensite -i /path/to/ensite-export.zip
```

CARTO's dry run reports discovered studies and maps. EnSite X prints its
import plan with field names and issues. The browser import queue offers
editable plans for both vendors. 7-Zip containers need the `sevenzip` extra.
For repeated CARTO CLI imports, unpack the archive once into a fixed directory:
study identity includes path context, and temporary archive-extraction paths
are not a stable cross-machine identifier. See the [CARTO](../guides/carto-import.md)
and [EnSite X](../guides/ensite-import.md) guides.

For a distributable example, substitute
`tests/fixtures/synthetic/carto/synthetic_study` or
`tests/fixtures/synthetic/ensite/synthetic_study` for the corresponding input.

Waveforms are optional. To import them, add `--waveforms --store-dir PATH`
and set `PULSE_EP_WAVEFORM_STORE_DIR` on the service to that same directory.

### Open the viewer

```bash
pulse-ep-server
```

Open `http://127.0.0.1:5000`, log in with the account created above and select
a study and map. The viewer supports scalar selection, colormaps,
measurement overlays and surface-area calculations.

## 3. Full Docker stack

```bash
cp .env.example .env
# Set PULSE_EP_JWT_SECRET_KEY and database credentials.
docker compose --profile server up -d --build
docker compose exec server pulse-ep-migrate
docker compose exec server pulse-ep-populate-colormaps
docker compose exec server pulse-ep-create-user --username admin --role admin
```

The server is available at `http://localhost:5000`. Run imports inside the
container after copying or mounting the export directory; see
[Docker deployment](../guides/docker-deployment.md). For existing databases,
apply `pulse-ep-migrate` after each software upgrade.

## Connect another analysis tool

The [client examples](../examples/index.md) describe authentication and use
from ParaView, R, MATLAB, Jupyter and Python. Each client needs an account on
the service; a `readonly` account suffices for data retrieval and calculations.
