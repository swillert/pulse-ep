# pulse-ep — Architecture

Internal engineering documentation. Behavioural / API-shape decisions
should land here first, then in the relevant module.

## 1 Mission

`pulse-ep` is a programmatic hub for electroanatomical mapping data. It
parses the proprietary exports of **CARTO 3** (Biosense Webster) and
**EnSiteX** (Abbott), persists them in a relational PostgreSQL database
under one vendor-neutral vocabulary, and exposes the data through three
independent surfaces:

- a JWT-authenticated REST API (Flask),
- a browser-based interactive 3D viewer (Three.js / WebGL), and
- a Python toolkit (`pulse_ep.core`) for custom analyses.

## 2 Package layout

| Subpackage | Role |
|---|---|
| `pulse_ep.core` | Domain models (`EPMap`, `Study`, `ScalarField`, `MeasurementPoint`, `PlacedPoint`), SQLAlchemy ORM, mesh processing, area integration, geodesic distances (Heat Method), map-vs-map comparison, the import queue and drop-directory watcher, typed config (`Settings`). |
| `pulse_ep.core.importers` | Everything vendor-specific: `carto`, `ensite`, the `lexicon` (per-vendor token → quantity), `source` (directory / ZIP transport) and `plan` (the reviewable `ImportPlan`). |
| `pulse_ep.server` | Flask app, JWT auth, REST API, the Three.js viewer and the import review UI (static frontend). |
| `pulse_ep.cli` | Console scripts: `pulse-ep-import-carto`, `pulse-ep-import-ensite`, `pulse-ep-populate-colormaps`, `pulse-ep-tag-maps`, `pulse-ep-create-user`, `pulse-ep-check-mesh`, `pulse-ep-extract-meshes`, `pulse-ep-server`, `pulse-ep-demo`. |
| `pulse_ep.figures` | Standard heatmap generators for clinical reports. |
| `pulse_ep.examples.demo_synthetic` | Self-contained end-to-end walkthrough on a synthetic atrium, wired as `pulse-ep-demo`. |

## 3 The import pipeline

```
ImportSource      DirSource | ZipSource — list / open / size / materialize.
  ↓               Parsers never assume a local filesystem layout, so upload
  ↓               and streaming machinery can sit in front unchanged.
VendorImporter    sniff() + parse() are required; prepare() / commit() are an
  ↓               OPTIONAL refinement. Callers go through prepare_plan() /
  ↓               commit_plan(), which fall back to parse() — never the
  ↓               methods directly.
ImportPlan        StudyPlan → MapPlan / WaveformPlan. Proposes what *would*
  ↓               be imported, with defaults pre-filled and issues flagged.
  ↓               No database writes. A human reviews and edits it.
Study / EPMap     Vendor-neutral domain objects.
  ↓
persist_study()   SQLAlchemy ORM → PostgreSQL.
```

Splitting `prepare` from `commit` puts "pre-fill as much as sensibly
possible" in exactly one place per vendor, and makes the proposal
inspectable before anything is written. Plans round-trip through JSON
(`plan_to_dict` / `plan_from_dict`), so a reviewer's edits can be stored
on an import job and executed later.

The queue (`ingest_queue`) drives that lifecycle over the `ImportJobModel`
state machine `detected → needs_review → importing → done | error`. The
drop-directory watcher, the REST layer and the review UI are thin: they
create jobs, read and edit `job.plan`, and call the queue. Commits are
idempotent by study identity, so rescanning a drop directory cannot
produce duplicates.

## 4 The vendor-neutral vocabulary

A value's meaning is decided **once, at import**, and carried explicitly —
never re-derived downstream. Two layers, deliberately kept apart:

- **The inventory** (`core.scalar_field.KIND_SPECS`) — what a quantity
  *is* and its unit. Closed and curated; a quantity is added once, for
  every vendor.
- **The lexicon** (`core.importers.lexicon`) — what each acquisition
  system *calls* it. Open-ended, one table per vendor, pure data.

A field is then **named by what it is**: `voltage_bipolar`,
`activation_time`. A name lookup and a kind lookup become the same
question, so one query spans a CARTO map and an EnSiteX map. (They used
to diverge: CARTO wrote `act` / `vol`, EnSiteX wrote `voltage_bipolar` —
the same quantity under two names, findable by neither. The old names
still resolve, through the lexicon, for studies imported before this.)

Two rules keep the vocabulary honest:

- **The lexicon is code, not configuration.** A wrong entry mislabels a
  clinical measurement silently, so it must be reviewed, tested and
  versioned with the parser. What belongs in the database is the
  *presentation* layer — label, colormap, default range per kind.
- **An unknown quantity survives.** A channel the lexicon does not
  recognise is still imported, under its raw vendor token with kind
  `unknown`, and stays visible for review. A closed vocabulary that drops
  the unfamiliar is how whole channels go missing.

Value-based decoding — CARTO's sign convention for its overloaded primary
slot, EnSiteX's export sentinels — inspects data rather than names and
stays in the vendor importer, not the lexicon.

## 5 Cross-cutting design choices

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

## 6 Repository conventions

- Repository name: `kebab-case` (`pulse-ep`).
- Python distribution: `pulse-ep`.
- Python package: `snake_case` (`pulse_ep`).
- Console scripts: prefix `pulse-ep-`.
- Versioning: SemVer, starting at `0.1.0`; `1.0.0` cuts when the
  accompanying software paper is accepted.

## 7 Quality gate

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
| Docs | `mkdocs-material` + `mkdocstrings` | ✓ (GitLab Pages) |

## 8 Data discipline

- **Schema additivity.** Alembic migrations stay additive. Existing
  production databases must run on every pulse-ep release without data
  loss.
- **No patient data in the open repository.** Tests and demos use
  synthetic meshes only; clinical data lives in private deployments.
- **Tests own the synthetic data.** `tests/conftest.py` and
  `src/pulse_ep/examples/demo_synthetic.py` are the only places that
  generate input data; downstream code is data-agnostic. The suite needs
  no live database: the ORM's PostgreSQL types (`JSONB`, `ARRAY`) cannot
  be created on SQLite, so persistence tests exercise the
  (de)serialisation converters directly.
- **`data/`, `drop/` and archive files are gitignored.** The GitHub
  mirror force-pushes every `main` commit to a public repository, so
  anything committed there is published irreversibly.
