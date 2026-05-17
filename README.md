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

## Quickstart

### 1. Synthetic walkthrough (no DB needed)

```bash
pulse-ep-demo
```

Builds a synthetic atrial mesh with a Gaussian score field, ingests it
into an in-memory SQLite, and prints the per-interval area breakdown.

### 2. Real CARTO study

```bash
# 1) start Postgres (Docker)
docker compose up -d db

# 2) import a study from a CARTO export folder
pulse-ep-import-carto /path/to/study-export.zip

# 3) seed default colormaps
pulse-ep-populate-colormaps

# 4) launch the web app
pulse-ep-server
# → http://localhost:5000
```

## Project structure

```
src/pulse_ep/
├── core/           # Domain (EPMap, Study), CARTO parsing, ORM, importer
├── cli/            # Console scripts for data ingestion and utilities
├── figures/        # Clinical / journal heatmap generators
├── server/         # Flask app, REST API, Three.js viewer
└── examples/       # Synthetic end-to-end demo
```

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
