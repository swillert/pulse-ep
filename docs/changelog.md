# Changelog

All notable changes to `pulse-ep` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **7-Zip import support.** CARTO exports are frequently 7-Zip archives named
  `.zip`; the container is now detected by content signature, so such an
  export imports without renaming. Needs the optional `pulse-ep[sevenzip]`
  extra.
- **VisiTag ablation sites** are read into study-level placed points, with RF
  parameters (duration, force, FTI, impedance drop, RF/ablation index).
  **The parser is unverified** — no real VisiTag export was available to test
  against — so it matches columns by name rather than position and yields no
  points at all when the columns are unrecognisable. The import plan flags any
  VisiTag file with that warning.

### Fixed

- CARTO `prepare` reported every per-point XML in an export as a failed study
  catalogue, drowning the plan in ~2000 spurious issues on a real export.

## [0.2.0] — 2026-09-06

### Added

- **EnSiteX (Abbott / St. Jude) import.** `SJM_DIF_5.0` mesh decode,
  per-vertex scalar fields, measurement points from every DxL channel,
  placed points (AutoMark / PFA / lesions / labels), chamber and CT
  anatomy (`Model_Groups.xml`, `difNNN.xml`), opt-in Parquet waveform
  storage, and the `pulse-ep-import-ensite` console script.
- **A reviewable import pipeline.** `ImportSource` (directory or ZIP),
  a vendor-importer registry with auto-detection, and a
  `prepare → review → commit` plan that proposes what would be imported —
  with issues flagged — before anything is written.
- **An import queue.** `ImportJobModel` state machine, a drop-directory
  watcher that waits for a bundle to fall quiescent, the
  `/api/import-jobs` REST layer and a browser review UI.
- **Map comparison.** `POST /api/compare` computes a delta field between
  two maps, with euclidean or geodesic correspondence; the latter uses a
  Heat Method solver (Crane et al. 2013).
- **A two-layer vocabulary.** An inventory of physical quantities
  (`KIND_SPECS`) plus a per-vendor lexicon of the tokens each system
  exports them under. Unrecognised quantities are imported under their
  raw vendor token rather than dropped.
- `GET /epmaps/<id>/scalars` — the quantities a map actually carries, so
  clients no longer have to assume field names.
- Alembic migrations, and the `PULSE_EP_DROP_DIR` /
  `PULSE_EP_WAVEFORM_STORE_DIR` settings.

### Changed

- **Scalar fields are named by the quantity they hold.** CARTO's `act`
  and `vol` became `activation_time` / `pacemap_score` and
  `voltage_bipolar`, matching EnSiteX, so one query spans both vendors.
  The old names still resolve for studies imported earlier.
- Analysis defaults resolve to a map's own primary quantity instead of
  the literal `"act"`, which only ever existed on CARTO maps.
- The viewer's data-type selector is populated from the map's real
  fields instead of a fixed ACT / VOL pair.
- CARTO gained `prepare`/`commit`, vendor-neutral measurement points, and
  no longer fails when no map filter is supplied.

- `docs/` — a full mkdocs-material documentation site, deployed via
  GitLab Pages.
- `ARCHITECTURE.md` — internal engineering documentation (module
  layout, design decisions, quality gate).
- Cross-language [examples](examples/index.md) for ParaView, R, MATLAB
  and Jupyter — each computing the per-vertex scalar histogram and the
  per-interval surface-area breakdown from the same REST payload.

### Changed

- `examples/` is now positioned as the cross-language reproducibility
  statement of the accompanying software paper.

### Removed

- `STRATEGY.md` — replaced by `ARCHITECTURE.md`. The cross-package
  strategy narrative is no longer part of this repository.
- `bootstrap-git.sh` — single-use Initial-commit helper, no longer
  needed.

## [0.1.0] — 2026-05-17

Initial open-source release. Extracted from the upstream
`pulse-ultimate` research codebase.

### Added

- `pulse_ep.core` — domain classes (`EPMap`, `Study`), CARTO 3 XML / mesh
  parsing, SQLAlchemy ORM models, importer, mesh processing, geodesic
  distances, surface-area integration.
- `pulse_ep.server` — Flask REST API + Three.js / WebGL 3D viewer.
- `pulse_ep.cli` — eight console scripts: `pulse-ep-server`,
  `pulse-ep-demo`, `pulse-ep-import-carto`, `pulse-ep-tag-maps`,
  `pulse-ep-populate-colormaps`, `pulse-ep-create-user`,
  `pulse-ep-check-mesh`, `pulse-ep-extract-meshes`.
- `pulse_ep.figures` — clinical heatmap generators (PDF / Excel / KML).
- `pulse_ep.examples.demo_synthetic` — self-contained synthetic
  end-to-end walkthrough, no PostgreSQL required.
- `pulse_ep.core.config.Settings` — typed configuration via
  `pydantic-settings`. Resolution order: env → `.env` → legacy
  `config.ini` → defaults.
- `compose.yaml` + `Dockerfile` — three-profile Docker stack
  (`default` = postgres only, `server` = + REST API, `admin` = + pgAdmin).
- GitLab CI matrix on Python 3.10 / 3.11 / 3.12, with `ruff` lint and
  `pytest` runs.
- Pre-commit configuration (`ruff`).
- `CITATION.cff` and MIT `LICENSE`.

### Notes

- Database schema is compatible with existing pulse-ultimate
  deployments — pulse-ep can read those databases without migration.
- Patient-identifiable data is **never** committed; all tests and
  demos run on synthetic meshes generated by
  `pulse_ep.examples.demo_synthetic`.
