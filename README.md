# pulse-ep

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20263542.svg)](https://doi.org/10.5281/zenodo.20263542)

An open-source platform for programmatic access to **electroanatomical
mapping data** from multiple vendors.

`pulse-ep` parses **CARTO 3** (Biosense Webster / Johnson & Johnson) and
**EnSite X** (Abbott) export archives into a relational
PostgreSQL database and exposes the data through four independent
surfaces:

- a **JWT-authenticated REST API** (Flask),
- a **browser-based interactive 3D viewer** (Three.js / WebGL),
- a **Python toolkit** (`pulse_ep.core`) for custom analyses — geodesic
  distances, surface-area integration, per-point catheter geometry, and
  per-vertex scalar fields, and
- an **MCP server** (`pulse-ep-mcp`) giving an AI client read-only access,
  **off unless switched on**, with study identity anonymised by default.
  Enabling it sends study data to a language model — check what your data
  permits before you do, and adapt what is sent where more is required.

The web viewer, MCP server and supplied analysis clients use the same REST
endpoints. The Python toolkit and import commands can also access PostgreSQL
directly or work with in-memory domain objects.

## Why?

Clinical mapping systems record ablation procedures as triangulated
chamber meshes with per-vertex activation times, bipolar voltages and
pace-mapping scores. They are excellent for real-time decision-making but
export data in vendor-specific formats. Reusing these exports across
research tools requires access to mesh geometry, measurements and signals
through documented data structures.

Worse, each vendor names the same physical quantity differently, so data
from two systems cannot be compared without a translation layer.
`pulse-ep` supplies one: every value is stored under **the name of the
quantity it holds** (`voltage_bipolar`, `activation_time`, …), decided
once at import from a per-vendor lexicon. One query then spans a CARTO
map and an EnSite X map alike.

From there, heterogeneous clients can analyse the data: Python and MATLAB
scripts, R workflows, Excel reports, the bundled web viewer, or an AI
assistant through the MCP server — all over the same REST endpoints.

## Architecture

```text
CARTO 3 / EnSite X exports
          │
          ▼
Vendor readers / import review ──► PostgreSQL + Parquet signal store
                                          │
                               ┌──────────┴──────────────┐
                               ▼                         ▼
                         Flask REST API          Python toolkit / CLI
                               │
             ┌─────────────────┼──────────────────────┐
             ▼                 ▼                      ▼
         Web viewer     ParaView / R / MATLAB    MCP server (opt-in)
                        Jupyter / Python               │
                                                      ▼
                                                  AI assistant
```

The Flask server connects to PostgreSQL. The web viewer, external REST
clients and MCP server connect to Flask; the Python toolkit and import
commands also support direct database access.

The vendor-neutral Python pipeline and drop-directory watcher auto-detect
exports and prepare a **reviewable import plan** (what would be imported,
with issues flagged). The browser review UI commits the plan after review.
The import commands also support direct import; the CARTO command's
`--dry-run` previews its input without offering an editable plan.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the internal engineering
documentation (module layout, design choices, quality gate).

## Installation

Python 3.10 or newer. PostgreSQL is required for persistent storage and the shared service.
The toolkit, in-memory vendor readers and synthetic walkthrough run without it.

### From source

`pulse-ep` is not on PyPI yet, so this is the way to install it:

```bash
git clone https://github.com/swillert/pulse-ep.git
cd pulse-ep
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

Check that it worked — no database, no configuration:

```bash
pulse-ep-demo
```

`[all]` is everything. Install less by naming the extras you want: `[server]`
for the REST API and the 3D viewer, `[figures]` for the report generators,
`[mcp]` for the MCP server, `[sevenzip]` for 7-Zip CARTO archives, `[dev]` for
the test and lint tooling, `[docs]` for the documentation site.

```bash
pip install -e ".[server,figures]"
```

### From a running database to a running server

`pulse-ep-init` writes
`.env` with a generated JWT secret, creates the waveform and drop directories,
applies the migrations, seeds the colormaps, creates an administrator and, on
request, a read-only account for the MCP server. It asks what it cannot work
out, and it is safe to re-run: an existing `.env` is kept, migrations run only
when behind, and an account that already exists is left alone with its password
unchanged.

```bash
docker compose up -d     # PostgreSQL, if you have none
pulse-ep-init
pulse-ep-server          # → http://localhost:5000
```

## Configuration

`pulse-ep` is configured via environment variables (12-factor style) using
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
All variables share the prefix `PULSE_EP_`; see [`.env.example`](.env.example)
for the full list.

[`pulse-ep-init`](#from-a-running-database-to-a-running-server) writes this
file, with a generated secret. By hand:

```bash
cp .env.example .env
# edit .env — at a minimum, set PULSE_EP_DATABASE_URL and PULSE_EP_JWT_SECRET_KEY
```

Resolution order (highest priority first):

1. Process environment (`PULSE_EP_*` variables)
2. `.env` file (path overridable via `PULSE_EP_ENV_FILE`)
3. Legacy `config.ini` (`PULSE_EP_CONFIG`)
4. Field defaults defined on `pulse_ep.core.config.Settings`

Docker Compose also reads `.env`, but uses `POSTGRES_*` variables to construct
the container database connection and overrides internal bind and storage paths.
See the [deployment guide](docs/guides/docker-deployment.md) when switching
between host and container commands.

## Quickstart

### 1. Synthetic walkthrough (no DB needed)

```bash
pulse-ep-demo
```

Builds an atrium-like ellipsoid, paints a Gaussian pace-mapping score field
onto it, wraps it as an `EPMap` — the same domain object the importers
produce — and prints the mesh size, the score distribution, the total surface
area and the area per score interval. It touches no database of any kind,
which is what makes it the first thing worth running after installing.

### 2. Vendor exports without patient data

```bash
examples/verify.sh
```

Reads the two synthetic exports in `tests/fixtures/synthetic/` — one CARTO 3,
one EnSite X — and prints mesh, fields, measurement points and surface area for
each. Their structure is derived from real exports, their content is generated;
both carry the same surface, so the two decode paths can be compared against
one another. See
[`tests/fixtures/synthetic/README.md`](tests/fixtures/synthetic/README.md) for
what this establishes (the file formats) and what it cannot (that a field means
what we call it).

### 3. A real study (local Python install)

```bash
# 1) start Postgres (Docker)
docker compose up -d

# 2) configure and set up in one command: .env with a generated JWT secret,
#    the migrations, the default colormaps, an administrator — and, on
#    request, a read-only account for the MCP server
pulse-ep-init

# 3) import a study — folder or archive, either vendor
pulse-ep-import-carto  -i /path/to/carto-export-dir   # a directory
pulse-ep-import-ensite -i /path/to/ensite-export.zip --dry-run   # plan only
pulse-ep-import-ensite -i /path/to/ensite-export.zip

# 4) launch the web app
pulse-ep-server
# → http://localhost:5000
```

`--dry-run` inspects an export without writing to the database. The CARTO
command reports discovered studies and maps; the EnSite X command prints its
import plan, including fields and issues. The browser import queue provides
an editable review plan for both vendors.

Signal traces are **opt-in**. In the supported CARTO ECG exports, acquisition
points reference multichannel windows; several points can share a recording.

```bash
pulse-ep-import-carto -i /path/to/carto-export \
    --waveforms --store-dir /var/pulse/waveforms
```

They are stored as Parquet beside the database and read back through
`/waveforms/<id>/download`, the example clients, or the MCP server. Set
`PULSE_EP_WAVEFORM_STORE_DIR` on the service to the same directory used at import.

`pulse-ep-init --non-interactive` asks nothing and takes flags instead, for
a scripted install; it is idempotent, so running it again after an upgrade
is a reasonable thing to do.

### 4. Full Docker stack

```bash
cp .env.example .env  # set PULSE_EP_JWT_SECRET_KEY at a minimum

# Bring up Postgres and the API server in one go.
docker compose --profile server up -d --build

# Initialise the schema, default colormaps and an administrator.
docker compose exec server pulse-ep-migrate
docker compose exec server pulse-ep-populate-colormaps
docker compose exec server pulse-ep-create-user --username admin --role admin

# Optional: pgAdmin on http://localhost:8080
docker compose --profile admin up -d
```

Stop everything with `docker compose down`; add `-v` to also wipe the
Postgres volume.

## Project structure

```
src/pulse_ep/
├── core/
│   ├── importers/  # Per-vendor decode: carto, carto_signal, ensite, the
│   │               #   lexicon, ImportSource (dir/ZIP) and the ImportPlan
│   ├── ...         # EPMap, Study, ScalarField, MeasurementPoint,
│   │               #   PlacedPoint, comparison, geodesic, interpolation,
│   │               #   waveform storage, roles, ORM models
│   └── ingest_*    # Import queue + drop-directory watcher
├── cli/            # Console scripts: init, import, migrate, users, utilities
├── figures/        # Clinical / journal heatmap generators
├── mcp/            # MCP server: read-only tools, the anonymiser, REST client
├── migrations/     # Alembic revisions — they ship inside the package, so an
│                   #   installed deployment can run pulse-ep-migrate
├── server/         # Flask app, REST API, Three.js viewer, review UI, roles
└── examples/       # Synthetic end-to-end demo (pulse-ep-demo)

examples/           # Cross-language client examples — see examples/README.md
├── paraview/         Native source plugin, Programmable Source and VTU export
├── r/                httr2 REST client + rgl/ggplot demo
├── matlab/           webread/webwrite client + trisurf demo
├── notebooks/        Jupyter walkthrough (PyVista)
└── python/           REST waveform plotting and an MCP analysis over stdio
```

## Documentation

Full documentation — installation, configuration, per-vendor import
guides, REST reference and the data model — lives in [`docs/`](docs/).
Start with [Installation](docs/getting-started/installation.md) and the
[Quickstart](docs/getting-started/quickstart.md).

## Interoperability examples

The [`examples/`](examples/) directory supplies a **native ParaView source
plugin**, **R and MATLAB client functions**, a **Jupyter notebook**, a Python
waveform plot and an executable **MCP** tool workflow. The built-in web viewer
provides another way to inspect maps and calculate interval areas.

Clients retrieve data through the shared service. Histograms and custom
calculations operate on downloaded arrays; the interval-area examples call
the same server operation. Use the raw mesh representation for full stored
geometry, all fields and acquisition measurements. The paper's supplementary
verification additionally checks independent local surface-area calculations.

## Citation

If you use `pulse-ep` in academic work, please cite the archived release:

> Willert, S., Frank, D., & Lian, E. *pulse-ep: An open-source platform for
> programmatic access to multivendor electroanatomical mapping data.*
> Zenodo. <https://doi.org/10.5281/zenodo.20263542>

That is the **concept DOI** — it always resolves to the latest release. To
pin an exact version, use that release's own DOI instead. Machine-readable
metadata is in [CITATION.cff](CITATION.cff); the accompanying software paper
is in preparation for SoftwareX.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issue tracker: [GitHub Issues](https://github.com/swillert/pulse-ep/issues).
PRs welcome; please run `ruff check .`, `ruff format --check .` and
`pytest` before opening one.
