# pulse-ep

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20263542.svg)](https://doi.org/10.5281/zenodo.20263542)

An open-source platform for programmatic access to **electroanatomical
mapping data** from multiple vendors.

`pulse-ep` parses **CARTO 3** (Biosense Webster / Johnson & Johnson) and
**EnSiteX** (Abbott / St. Jude) export archives into a relational
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

Each is a client of the same REST endpoints; none has a privileged path
into the database.

## Why?

Clinical mapping systems record ablation procedures as triangulated
chamber meshes with per-vertex activation times, bipolar voltages and
pace-mapping scores. They are excellent for real-time decision-making but
provide **no programmatic interface** — quantitative research requires
external access to raw mesh geometry and measurement-point coordinates.

Worse, each vendor names the same physical quantity differently, so data
from two systems cannot be compared without a translation layer.
`pulse-ep` supplies one: every value is stored under **the name of the
quantity it holds** (`voltage_bipolar`, `activation_time`, …), decided
once at import from a per-vendor lexicon. One query then spans a CARTO
map and an EnSiteX map alike.

From there, heterogeneous clients can analyse the data: Python and MATLAB
scripts, R workflows, Excel reports, the bundled web viewer, or an AI
assistant through the MCP server — all over the same REST endpoints.

## Architecture

```
CARTO export  ─┐   ┌────────────────────────────────────────────────┐
               ├──►│ pulse_ep.core.importers                        │
EnSiteX export┘   │   sniff → prepare → (human review) → commit     │──► PostgreSQL
   (folder/ZIP)    │   vendor decode + lexicon → vendor-neutral      │
                   └────────────────────────────────────────────────┘
                                       │
        ┌───────────────┬──────────────┴───────┬──────────────────────┐
        ▼               ▼                      ▼                      ▼
  pulse_ep.server   pulse_ep.mcp         pulse_ep.cli          pulse_ep.core
  Flask + JWT,      read-only tools      init, import_carto,   EPMap, Study,
  Three.js viewer,  for an AI client,    import_ensite,        ScalarField,
  REST API,         off unless           migrate, tag_maps,    MeasurementPoint,
  import review UI, enabled, anonymised  populate_colormaps,   interpolation,
  HTML reports      by default           create_user, demo     geodesic, waveform
```

The server, the viewer, the toolkit and the MCP server are **peers**: each
is a client of the same JWT REST endpoints, and none has a privileged path
into the database.

An export is auto-detected, turned into a **reviewable import plan**
(what would be imported, with issues flagged), and only written once the
plan is committed — by CLI, or through the drop-directory watcher and the
browser review UI.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the internal engineering
documentation (module layout, design choices, quality gate).

## Installation

```bash
# core: import, models, CLI utilities
pip install pulse-ep

# add the Flask server + 3D viewer
pip install "pulse-ep[server]"

# add the figure / report generation extras
pip install "pulse-ep[figures]"

# add the MCP server (read-only access for an AI client)
pip install "pulse-ep[mcp]"

# everything (server, figures, MCP, dev tools)
pip install "pulse-ep[all]"
```

### From source

```bash
git clone https://gitlab.willert.net/sw/pulse-ep.git
cd pulse-ep
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

## Configuration

`pulse-ep` is configured via environment variables (12-factor style) using
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
All variables share the prefix `PULSE_EP_`; see [`.env.example`](.env.example)
for the full list.

```bash
pulse-ep-init          # writes .env, generates the secret, and sets the rest up
```

or by hand:

```bash
cp .env.example .env
# edit .env — at a minimum, set PULSE_EP_DATABASE_URL and PULSE_EP_JWT_SECRET_KEY
```

Resolution order (highest priority first):

1. Process environment (`PULSE_EP_*` variables)
2. `.env` file (path overridable via `PULSE_EP_ENV_FILE`)
3. Legacy `config.ini` (`PULSE_EP_CONFIG`)
4. Field defaults defined on `pulse_ep.core.config.Settings`

The same `.env` file is consumed by `docker compose` (see below), so a
single source of truth covers both local development and the Docker stack.

## Quickstart

### 1. Synthetic walkthrough (no DB needed)

```bash
pulse-ep-demo
```

Builds a synthetic atrial mesh with a Gaussian score field, ingests it
into an in-memory SQLite, and prints the per-interval area breakdown.

### 2. Vendor exports without patient data

```bash
examples/verify.sh
```

Reads the two synthetic exports in `tests/fixtures/synthetic/` — one CARTO 3,
one EnSiteX — and prints mesh, fields, measurement points and surface area for
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

# 3) import a study — folder or ZIP, either vendor
pulse-ep-import-carto  -i /path/to/carto-export-dir   # a directory
pulse-ep-import-ensite -i /path/to/ensite-export.zip --dry-run   # plan only
pulse-ep-import-ensite -i /path/to/ensite-export.zip

# 4) launch the web app
pulse-ep-server
# → http://localhost:5000
```

`--dry-run` prints the import plan — which maps, which scalar fields, how
many points, and any issues detected — without writing anything. Run it
first on an unfamiliar export.

Signal traces are **opt-in**, because they dwarf the rest of an export: a
CARTO study writes one 2.5 s window of every channel per acquired point.

```bash
pulse-ep-import-carto -i /path/to/carto-export \
    --waveforms --store-dir /var/pulse/waveforms
```

They are stored as Parquet beside the database (about twenty times smaller
than the exported text) and read back through
`/waveforms/<id>/download`, the example clients, or the MCP server.

`pulse-ep-init --non-interactive` asks nothing and takes flags instead, for
a scripted install; it is idempotent, so running it again after an upgrade
is a reasonable thing to do.

### 4. Full Docker stack

```bash
cp .env.example .env  # set PULSE_EP_JWT_SECRET_KEY at a minimum

# Bring up Postgres and the API server in one go.
docker compose --profile server up -d --build

# One-off setup inside the running server container: migrations, colormaps
# and an administrator (or just pulse-ep-create-user for the account alone).
docker compose exec server pulse-ep-init --non-interactive --admin-user admin

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
├── paraview/         ParaView Programmable Source + CLI .vtu export
├── r/                httr2 REST client + rgl/ggplot demo
├── matlab/           webread/webwrite client + trisurf demo
├── notebooks/        Jupyter walkthrough (PyVista)
└── python/           MCP clients over stdio (analysis, signal plotting)
```

## Documentation

Full documentation — installation, configuration, per-vendor import
guides, REST reference and the data model — is at
<https://sw.gitlab-pages.willert.net/pulse-ep/>, and its sources live in
[`docs/`](docs/). Start with
[Installation](docs/getting-started/installation.md) and the
[Quickstart](docs/getting-started/quickstart.md).

## Interoperability examples

`pulse-ep` is designed as a programmatic hub, not just a Python library.
The [`examples/`](examples/) directory shows how to consume the REST API
from **ParaView**, **R**, **MATLAB** and **Jupyter**, and is structured
as the **cross-language reproducibility statement of the software paper**:
identical inputs (one REST payload per map) produce identical platform
reductions — the per-vertex scalar histogram and the per-interval
surface-area breakdown — in four independent toolchains. The bundled
web viewer is a fifth.

[`examples/python/`](examples/python/) drives the **MCP server** over stdio
instead: one client reproduces an aggregate analysis through the tools, the
other plots a point's own signal window. They are shown separately because
they are a different transport, not a fifth reproduction of the paper's
reduction.

## Citation

If you use `pulse-ep` in academic work, please cite the archived release:

> Willert, S., Lian, E., & Frank, D. *pulse-ep: An open-source platform for
> programmatic access to multivendor electroanatomical mapping data.*
> Zenodo. <https://doi.org/10.5281/zenodo.20263542>

That is the **concept DOI** — it always resolves to the latest release. To
pin an exact version, use that release's own DOI instead. Machine-readable
metadata is in [CITATION.cff](CITATION.cff); the accompanying software paper
is in preparation for SoftwareX.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issue tracker: [GitLab Issues](https://gitlab.willert.net/sw/pulse-ep/-/issues).
PRs welcome; please run `ruff check .`, `ruff format --check .` and
`pytest` before opening one.
