# pulse-ep

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20263542.svg)](https://doi.org/10.5281/zenodo.20263542)

An open-source platform for programmatic access to **electroanatomical
mapping data** from multiple vendors.

`pulse-ep` parses **CARTO 3** (Biosense Webster / Johnson & Johnson) and
**EnSiteX** (Abbott / St. Jude) export archives into a relational
PostgreSQL database and exposes the data through three independent
surfaces:

- a **JWT-authenticated REST API** (Flask),
- a **browser-based interactive 3D viewer** (Three.js / WebGL), and
- a **Python toolkit** (`pulse_ep.core`) for custom analyses — geodesic
  distances, surface-area integration, per-point catheter geometry, and
  per-vertex scalar fields.

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
scripts, R workflows, Excel reports, or the bundled web viewer.

## Architecture

```
CARTO export  ─┐   ┌────────────────────────────────────────────────┐
               ├──►│ pulse_ep.core.importers                        │
EnSiteX export┘   │   sniff → prepare → (human review) → commit     │──► PostgreSQL
   (folder/ZIP)    │   vendor decode + lexicon → vendor-neutral      │
                   └────────────────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  pulse_ep.server                pulse_ep.cli                   pulse_ep.core
  Flask + JWT,                   import_carto,                  EPMap, Study,
  Three.js viewer,               import_ensite,                 ScalarField,
  REST API,                      tag_maps,                      MeasurementPoint,
  import review UI,              populate_colormaps,            geodesic, comparison,
  HTML reports                   check_mesh, demo               SQLAlchemy models
```

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

# everything (server, figures, dev tools)
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

### 2. A real study (local Python install)

```bash
# 1) start Postgres (Docker)
docker compose up -d

# 2) configure the connection
cp .env.example .env
# edit PULSE_EP_DATABASE_URL and PULSE_EP_JWT_SECRET_KEY

# 3) create the schema
alembic upgrade head

# 4) import a study — folder or ZIP, either vendor
pulse-ep-import-carto  /path/to/carto-export.zip
pulse-ep-import-ensite -i /path/to/ensite-export.zip --dry-run   # plan only
pulse-ep-import-ensite -i /path/to/ensite-export.zip

# 5) seed default colormaps and create an admin user
pulse-ep-populate-colormaps
pulse-ep-create-user --username admin --role admin

# 6) launch the web app
pulse-ep-server
# → http://localhost:5000
```

`--dry-run` prints the import plan — which maps, which scalar fields, how
many points, and any issues detected — without writing anything. Run it
first on an unfamiliar export.

### 3. Full Docker stack

```bash
cp .env.example .env  # set PULSE_EP_JWT_SECRET_KEY at a minimum

# Bring up Postgres and the API server in one go.
docker compose --profile server up -d --build

# One-off admin user (runs inside the running server container).
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
│   ├── importers/  # Per-vendor decode: carto, ensite, the lexicon,
│   │               #   ImportSource (dir/ZIP) and the ImportPlan
│   ├── ...         # EPMap, Study, ScalarField, MeasurementPoint,
│   │               #   PlacedPoint, comparison, geodesic, ORM models
│   └── ingest_*    # Import queue + drop-directory watcher
├── cli/            # Console scripts for data ingestion and utilities
├── figures/        # Clinical / journal heatmap generators
├── server/         # Flask app, REST API, Three.js viewer, review UI
└── examples/       # Synthetic end-to-end demo (pulse-ep-demo)

alembic/            # Database schema migrations

examples/           # Cross-language client examples — see examples/README.md
├── paraview/         ParaView Programmable Source + CLI .vtu export
├── r/                httr2 REST client + rgl/ggplot demo
├── matlab/           webread/webwrite client + trisurf demo
└── notebooks/        Jupyter walkthrough (PyVista)
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
