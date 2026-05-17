# pulse-ep — Architecture

Internal engineering documentation. Behavioural / API-shape decisions
should land here first, then in the relevant module.

## 1 Mission

`pulse-ep` is a programmatic hub for CARTO 3 electroanatomical mapping
data. It parses the proprietary export, persists it in a relational
PostgreSQL database, and exposes the data through three independent
surfaces:

- a JWT-authenticated REST API (Flask),
- a browser-based interactive 3D viewer (Three.js / WebGL), and
- a Python toolkit (`pulse_ep.core`) for custom analyses.

## 2 Package layout

| Subpackage | Role |
|---|---|
| `pulse_ep.core` | Domain models (`EPMap`, `Study`), CARTO-XML / mesh parsing, SQLAlchemy ORM, importer, mesh processing, area integration, geodesic distances, typed config (`Settings`). |
| `pulse_ep.server` | Flask app, JWT auth, REST API, the Three.js viewer (static frontend). |
| `pulse_ep.cli` | Console scripts: `pulse-ep-import-carto`, `pulse-ep-populate-colormaps`, `pulse-ep-tag-maps`, `pulse-ep-create-user`, `pulse-ep-check-mesh`, `pulse-ep-extract-meshes`, `pulse-ep-server`, `pulse-ep-demo`. |
| `pulse_ep.figures` | Standard heatmap generators for clinical reports. |
| `pulse_ep.examples.demo_synthetic` | Self-contained end-to-end walkthrough on a synthetic atrium, wired as `pulse-ep-demo`. |

## 3 Cross-cutting design choices

- **Lazy initialisation everywhere.** Importing `pulse_ep` must not
  require a database connection or a configured server. `engine` and
  `Session` are constructed on first use; failure surfaces at the call
  site, not at import time. The same pattern applies in
  `pulse_ep.server.app` — the module is importable without a JWT
  secret, falling back to a clearly insecure dev placeholder with a
  runtime warning.
- **12-factor configuration.** All settings live in
  `pulse_ep.core.config.Settings` (pydantic-settings). Resolution
  order: process env (`PULSE_EP_*`) → `.env` file → legacy
  `config.ini` (for backwards compatibility) → field defaults.
  Secrets (`SecretStr`) never appear in `repr()`.
- **Optional extras as functional capabilities.** `pulse-ep` (core
  data + CLI) installs slim; `pulse-ep[server]` adds Flask / JWT /
  gunicorn; `pulse-ep[figures]` adds reportlab / openpyxl /
  simplekml; `pulse-ep[dev]` adds the test and lint tooling.
  Heavyweight, optional dependencies stay out of the core install.
- **REST first.** The bundled web viewer is a client of the same
  endpoints the `examples/` directory consumes. There is
  no privileged "internal" API; every reader can be substituted.

## 4 Repository conventions

- Repository name: `kebab-case` (`pulse-ep`).
- Python distribution: `pulse-ep`.
- Python package: `snake_case` (`pulse_ep`).
- Console scripts: prefix `pulse-ep-`.
- Versioning: SemVer, starting at `0.1.0`; `1.0.0` cuts when the
  accompanying software paper is accepted.

## 5 Quality gate

| Concern | Tool | Status |
|---|---|---|
| Build | setuptools (PEP 621 `pyproject.toml`) | ✓ |
| Lint + format | `ruff check` + `ruff format` | ✓ |
| Typing | `mypy` | dev-extra, gradual |
| Tests | `pytest` (+ `pytest-cov`) | ✓ |
| Pre-commit | `pre-commit` | ✓ |
| CI | GitLab CI matrix 3.10 / 3.11 / 3.12 | ✓ |
| Citation | `CITATION.cff` | ✓ |
| License | MIT (`LICENSE`) | ✓ |
| Docs | `mkdocs-material` + `mkdocstrings` | planned |

## 6 Data discipline

- **Schema additivity.** Alembic migrations stay additive. Existing
  production databases must run on every pulse-ep release without data
  loss.
- **No patient data in the open repository.** Tests and demos use
  synthetic meshes only; clinical data lives in private deployments.
- **Tests own the synthetic data.** `tests/conftest.py` and
  `src/pulse_ep/examples/demo_synthetic.py` are the only places that
  generate input data; downstream code is data-agnostic.
