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
| `pulse_ep.core` | Domain models (`EPMap`, `Study`, `ScalarField`, `MeasurementPoint`, `PlacedPoint`), SQLAlchemy ORM, mesh processing, area integration, geodesic distances (Heat Method), scattered-data `interpolation`, map-vs-map comparison, out-of-database `waveform` storage, the role vocabulary, the import queue and drop-directory watcher, typed config (`Settings`). |
| `pulse_ep.core.importers` | Everything vendor-specific: `carto`, `carto_signal` (its per-point ECG windows), `ensite`, the `lexicon` (per-vendor token → quantity), `source` (directory / ZIP / 7-Zip transport) and `plan` (the reviewable `ImportPlan`). |
| `pulse_ep.server` | Flask app, JWT auth and role enforcement, REST API, the Three.js viewer and the import review UI (static frontend). |
| `pulse_ep.mcp` | The MCP server: read-only tools for an AI client, the anonymiser that decides what may leave the deployment, and a REST client — it holds no privileged path of its own. |
| `pulse_ep.migrations` | Alembic revisions, shipped inside the package so an installed deployment can run `pulse-ep-migrate` without a source checkout. |
| `pulse_ep.cli` | Console scripts: `pulse-ep-init`, `pulse-ep-import-carto`, `pulse-ep-import-ensite`, `pulse-ep-migrate`, `pulse-ep-populate-colormaps`, `pulse-ep-tag-maps`, `pulse-ep-create-user`, `pulse-ep-check-mesh`, `pulse-ep-extract-meshes`, `pulse-ep-server`, `pulse-ep-mcp`, `pulse-ep-demo`. |
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
  simplekml; `pulse-ep[mcp]` adds the MCP SDK; `pulse-ep[dev]` adds the
  test and lint tooling. Heavyweight, optional dependencies stay out of
  the core install, and the package imports without any of them.
- **REST first.** The bundled web viewer, the `examples/` clients and
  the MCP server are all clients of the same endpoints. There is no
  privileged "internal" API; every reader can be substituted.
- **Who may do what is enforced, not annotated.** The JWT's `role` claim
  decides: `admin`, `user`, and `readonly` — refused on every endpoint
  that changes stored state, which is what makes a read-only account for
  an AI client a property of the deployment rather than a promise in a
  document. Reads that arrive as `POST` stay open, because what decides
  is what an endpoint does, not the verb it came under.
- **What leaves the deployment is decided deliberately.** A study is
  named after its export, and a real one carries a case number and
  initials — so MCP results are anonymised by default, aliased to the
  database id, and the switch is the operator's alone: no tool can lift
  it. AI access itself is **opt-in**: `PULSE_EP_MCP_ENABLED=1` at both
  ends, refused while unset and on any value that is not recognised, so
  a typo cannot enable it. Both switches fail towards sending nothing,
  because what an operator must decide before turning this on — which
  rules govern the data, and whether anonymised study names are enough —
  is not a question the software can answer for them.

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
| CI | GitLab CI matrix 3.10 … 3.14 | ✓ |
| Citation | `CITATION.cff` | ✓ |
| License | MIT (`LICENSE`) | ✓ |
| Docs | `mkdocs-material` + `mkdocstrings` | ✓ (GitLab Pages) |

## 8 Data discipline

- **Schema additivity.** Alembic migrations stay additive. Existing
  production databases must run on every pulse-ep release without data
  loss.
- **No patient data in the open repository.** Tests and demos use
  synthetic meshes only; clinical data lives in private deployments.
- **Tests own the data they run on.** `tests/conftest.py`,
  `src/pulse_ep/examples/demo_synthetic.py` and the shipped synthetic
  exports under `tests/fixtures/synthetic/` supply it, and a test that
  needs a particular shape — a folded surface, a mesh with a reordered
  colour section — builds it inline. Nothing reads an external export, and
  downstream code stays data-agnostic. The suite needs no live database:
  the ORM's PostgreSQL types (`JSONB`, `ARRAY`) cannot be created on
  SQLite, so persistence tests exercise the (de)serialisation converters
  directly and route tests use Flask's test client.
- **`data/`, `drop/` and archive files are gitignored.** The GitHub
  mirror force-pushes every `main` commit to a public repository, so
  anything committed there is published irreversibly.
