# pulse-ep

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

An open-source platform for programmatic access to **CARTO 3**
electroanatomical mapping data — the successor to
[pulse-ultimate](https://gitlab.willert.net/sw/pulse-ultimate).

`pulse-ep` parses CARTO 3 (Biosense Webster / Johnson & Johnson) export
archives into a relational PostgreSQL database and exposes the data
through three independent surfaces:

- a **JWT-authenticated REST API** (Flask),
- a **browser-based interactive 3D viewer** (Three.js / WebGL), and
- a **Python toolkit** (`pulse_ep.core`) for custom analyses — geodesic
  distances, surface-area integration, per-point catheter geometry, and
  per-vertex scalar fields.

Quantitative methods that build on top of `pulse-ep` — Heat Method
geodesics, Gaussian decay fits, σ-validation — live in the companion
package [`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay).

## Why?

CARTO 3 records ablation procedures as triangulated chamber meshes with
per-vertex activation times, bipolar voltages, and pace-mapping similarity
scores. It is excellent for real-time clinical decision-making but
provides **no programmatic interface** — quantitative research requires
external access to raw mesh geometry and measurement-point coordinates.

`pulse-ep` turns the proprietary archive into a queryable hub. From there,
heterogeneous clients can analyse the data: Python and MATLAB scripts,
R workflows, Excel reports, or the bundled web viewer.

## Architecture

```
                ┌─────────────────────────────────────────────────┐
CARTO export ──►│  pulse_ep.core.importer   (XML + mesh parsing)  │──► PostgreSQL
                └─────────────────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  pulse_ep.server                pulse_ep.cli                   pulse_ep.core
  Flask + JWT,                   import_carto,                  EPMap, Study,
  Three.js viewer,               tag_maps,                      mesh_proc,
  REST API,                      populate_colormaps,            xml_proc,
  HTML reports                   check_mesh, demo               SQLAlchemy models
```

The optional scientific layer is in a **separate package**:

```
                        pulse-ep-decay  (independent install)
        ┌───────────────────────────────────────────────────────────┐
        │  geodesic · heatmethod · decay_fit · validation           │
        │  + optional pulse_ep_decay.integration.pulse_ep adapter   │
        └───────────────────────────────────────────────────────────┘
```

`pulse-ep` never imports from `pulse-ep-decay`; the decay package imports
from `pulse-ep` only inside the optional adapter submodule. This keeps the
platform install slim and the scientific kernel independently reproducible.

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

For the scientific σ-resolution analysis, install the companion package:

```bash
pip install pulse-ep-decay
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
3. Legacy `config.ini` (`PULSE_EP_CONFIG`) — kept for pulse-ultimate compatibility
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

### 2. Real CARTO study (local Python install)

```bash
# 1) start Postgres (Docker)
docker compose up -d

# 2) configure the connection
cp .env.example .env
# edit PULSE_EP_DATABASE_URL and PULSE_EP_JWT_SECRET_KEY

# 3) import a study from a CARTO export folder
pulse-ep-import-carto /path/to/study-export.zip

# 4) seed default colormaps and create an admin user
pulse-ep-populate-colormaps
pulse-ep-create-user --username admin --role admin

# 5) launch the web app
pulse-ep-server
# → http://localhost:5000
```

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
├── core/           # Domain (EPMap, Study), CARTO parsing, ORM, importer
├── cli/            # Console scripts for data ingestion and utilities
├── figures/        # Clinical / journal heatmap generators
├── server/         # Flask app, REST API, Three.js viewer
└── examples/       # Synthetic end-to-end demo (pulse-ep-demo)

examples/           # Cross-language client examples — see examples/README.md
├── paraview/         ParaView Programmable Source + CLI .vtu export
├── r/                httr2 REST client + rgl/ggplot demo
├── matlab/           webread/webwrite client + trisurf demo
└── notebooks/        Jupyter walkthrough (PyVista)
```

## Interoperability examples

`pulse-ep` is designed as a programmatic hub, not just a Python library.
The [`examples/`](examples/) directory shows how to consume the REST API
from **ParaView**, **R**, **MATLAB** and **Jupyter**, and is structured
as the **cross-language reproducibility statement of the software paper**:
identical inputs (one REST payload per map) produce identical platform
reductions — the per-vertex scalar histogram and the per-interval
surface-area breakdown — in four independent toolchains. The bundled
web viewer is a fifth.

The scientific σ-resolution analysis (Heat-Method geodesics + Gaussian
decay fit) is a separate contribution and lives in
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay), which
ships its own cross-language reproducibility demos for σ̂.

## Citation

If you use `pulse-ep` in academic work, please cite the
[CITATION.cff](CITATION.cff) entry. The accompanying software paper is in
preparation for SoftwareX.

## License

MIT — see [LICENSE](LICENSE).

## Related

- [`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay) —
  scientific extension package (Heat Method, σ-resolution analysis).
- [`pulse-ultimate`](https://gitlab.willert.net/sw/pulse-ultimate) —
  predecessor monorepo, frozen for paper reproducibility.

## Contributing

Issue tracker: [GitLab Issues](https://gitlab.willert.net/sw/pulse-ep/-/issues).
PRs welcome; please run `ruff check` and `pytest` before opening one.
