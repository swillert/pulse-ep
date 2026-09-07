# Changelog

All notable changes to `pulse-ep` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.3] — 2026-09-07

What a fresh installation found. The 0.4.2 audit read the documentation
against the implementation; this one installed the package into an empty
directory and ran what the documentation says to run.

### Fixed

- **Mirroring to GitHub could rewind the public branch.** The job pushed its
  own pipeline's `HEAD` with `--force`, and jobs are not ordered: with a
  single runner an older pipeline can reach the deploy stage after a newer one
  has already mirrored. On 2026-09-07 pipeline #510 undid #512 that way, and
  two commits were missing from the public repository until the next push. It
  pushes the current tip of `main` now, without `--force`, so a stale push is
  refused rather than destroying history — at the price that a commit made
  directly on GitHub blocks mirroring until someone resets that branch.

- The Docker image applies versioned migrations before starting its workers.
  Creating tables first had caused the documented first-time migration to
  fail with duplicate-table errors.
- Migration configuration preserves percent-encoded database passwords.
- The shipped Jupyter notebook uses its documented static rendering backend
  and labels histograms with the retrieved quantity instead of a fixed `act`.
- CARTO import plans now respect a completely deselected map list,
  study-specific selections when map names repeat, exact map names and the
  option to omit acquisition points. Previously an empty selection imported
  every map, and a selected name could also include a deselected map in
  another study.
- The MATLAB interval-area client now preserves the nested request shape
  for a single interval as well as multiple intervals. Empty bins return
  zero; the R and MATLAB client comments now state this correctly.
- The data-model reference identifies stored triangle areas as mm² and
  distinguishes them from analysis results in cm².
- The CARTO import guide now describes CARTO; it had contained the EnSite X
  guide. It documents catalogue-only preparation, quantity inference and the
  whole-database scope of `--clear`.
- The README distinguishes direct CLI imports from reviewed import plans.
  The example login command correctly escapes special characters in credentials.
- Release instructions use a new version as an example instead of the
  already existing v0.4.2 tag.

## [0.4.2] — 2026-09-07

A release audit: the README, the guides, the example instructions and the
manuscript were read against the implementation, and what did not match was
corrected in whichever of the two was wrong. Most of it was documentation, but
not all.

### Security

- **`pulse-ep-check-mesh` carried a hard-coded username and password** and
  printed the access token it received. The account was a real one, the file
  has been in the repository since the initial commit, and CI mirrors `main`
  to a public GitHub repository — so the credential is published and removing
  it here does not unpublish it. **Anyone who used that password anywhere must
  change it.** The command now takes `--username` or `PULSE_EP_USERNAME`, reads
  the password from `PULSE_EP_PASSWORD` or a prompt, and never prints the
  token.
- **A ZIP member could write outside the directory it was unpacked into.**
  `ZipSource.materialize` joined the archive's own member names onto the
  destination, so `../`, an absolute path, a Windows drive letter or a symlink
  already present in an explicitly supplied destination would place the file
  elsewhere. Every member is now checked before any of them is written, so a
  hostile archive aborts the extraction rather than leaving half of it behind.
- **Malformed login and registration requests reached the database layer.**
  A non-object body, or a username that was not a string, produced a 500 where
  it should produce a 400; a duplicate username produced one too. The role
  escalation guard is unchanged — an unauthenticated caller still cannot ask
  for a privileged role.

### Fixed

- **A shared triangle edge counted twice in geodesic comparison.**
  `coo_matrix` sums duplicate entries, and an interior edge is contributed by
  both of its triangles — so it entered the graph at twice its length while a
  boundary edge kept its own. Every geodesic distance across a mesh interior
  was inflated, and with it the distance-based masking that decides which
  vertices are compared at all.
- **A 7-Zip member's name was joined onto the extraction root unchecked.**
  py7zr drops the anchor when it extracts, and CARTO archives do carry
  absolute entries, so `root / "/var/tmp/export/Study.xml"` resolved to
  `/var/tmp/export/Study.xml` — Python's `/` discards the left side against an
  absolute right side. The reader was opening the *original* file rather than
  the extracted copy, and would have failed once the original was gone.
- **`pulse-ep-init` returned generated settings without writing them.** When
  an existing `.env` was kept, a freshly generated JWT secret existed only in
  that process — the server started afterwards had none. Absent keys are
  written now, standard dotenv quoting is read and preserved, and the file is
  tightened to mode 600 whether or not this run added to it. It also says so
  when the file or the environment overrides an explicitly requested `--mcp`,
  instead of dropping the request silently.
- **Replacing an EnSite X study left its dependent rows behind.** Waveform and
  legacy point rows were not deleted with the study, so a re-import
  accumulated them. `pulse-ep-import-carto --clear` now drops every table the
  ORM declares rather than a hand-maintained list that had fallen behind.
- **Importing EnSite X signals without a store failed after writing.**
  `--waveforms` now requires `--store-dir` before anything is read.
- The demo registers its synthetic score as a `pacemap_score` field in percent,
  so it carries the same self-description an imported map does.
- The generated MCP client configuration sets `PULSE_EP_MCP_ENABLED=1`, which
  the client needs since 0.4.0 and did not receive. An unrecognised value
  disables access without preventing the server from starting.
- Account creation honours the configured bcrypt work factor on all three
  paths that hash a password.
- The Docker image installs the reporting and 7-Zip extras it was documented
  as having, renders without a display, and mounts writable, persistent
  directories for reports, waveforms and the drop directory.
- **GitHub mirroring pushed `HEAD` as `main` from tag pipelines**, so tagging
  an older commit would have rewound the public branch, and it force-pushed
  tags, which can overwrite a published release. Neither happens now.
- Installation, the demo, command options, roles, API responses, signal
  handling, viewer behaviour and the client examples were reconciled with the
  implementation; obsolete SQLite claims and instructions for clients that do
  not exist were removed.

### Changed

- The citation author order is Sven Willert, Derk Frank, Evgeny Lian.
- `pulse-ep-demo` stores its triangle areas in mm², the unit every importer
  writes and `/get_mesh_data` declares.
- One definition of what "on" means (`config.TRUE_VALUES`), shared by
  `Settings`, `pulse-ep-mcp` and `pulse-ep-init`, so the three cannot drift
  apart on a switch whose failure direction decides whether study data reaches
  a language model.
- English throughout the reader-facing material: the verification script's
  output, the synthetic-fixture and publication notes. The vendor is written
  **EnSite X**, as Abbott writes it.
- Generated documentation and local waveform stores are ignored.

## [0.4.1] — 2026-09-07

### Fixed

- **The project pointed at an address most readers cannot reach.** Homepage,
  Repository, Issues and Documentation in the package metadata,
  `repository-code` in `CITATION.cff`, and the clone commands and file links
  throughout the README and `docs/` all named the self-hosted GitLab. The
  GitHub mirror is the open-access repository — it is what the SoftwareX
  submission and the Zenodo DOI workflow refer to, and what someone installing
  the package from PyPI actually has. They resolve there now.
  `docs/release-process.md` keeps its GitLab names, because there GitLab
  genuinely is the origin that mirrors to GitHub; so does `mkdocs.yml`, which
  still publishes to GitLab Pages.
- The README's documentation paragraph linked the GitHub tree of `docs/` and
  then `docs/` again as "its sources" — the same place twice.

### Changed

- `CITATION.cff`: author order, and the `preferred-citation` block is gone
  until the SoftwareX article has a bibliographic record — cite the software
  release in the meantime.
- The Python MCP example says that MCP access is off by default and what to
  establish before enabling it.

## [0.4.0] — 2026-09-07

### Changed

- **MCP access is opt-in.** `PULSE_EP_MCP_ENABLED` no longer defaults to on: a
  deployment serves an AI client only where it is set to `1` — at the server
  and in the MCP process both — and anything unrecognised, an empty value or a
  typo, leaves it off. 0.3 had it the other way round, failing open on the
  argument that the switch grants no access of its own. That is the wrong
  direction for this particular switch: what it governs is study data leaving
  the deployment for a language model, and a deployment that has never
  considered the question should not already be answering it.

    **Upgrading:** a 0.3 deployment that serves MCP without having set the
    variable stops serving it. Set `PULSE_EP_MCP_ENABLED=1` at both ends to
    restore access — after the check described below. Nothing else changes and
    no migration is involved; every other client is untouched.

- **What has to be established before enabling it is now written down**, in the
  MCP guide, the CLI reference, `.env.example`, and at the prompt
  `pulse-ep-init` asks the question at. Serving MCP sends study data to a
  language model — in most setups a third-party service, outside the systems
  the data was approved for — and whether that is permitted depends on rules
  this software cannot check: institutional policy on research and patient
  data, the terms and any ethics approval the studies were collected under, the
  agreement with the AI provider. Where those require more than the anonymiser
  provides — it replaces study names, paths and free-text fields, and sends map
  names, quantities and measured values unchanged — the software must be
  adapted to meet them **before** it is switched on. Anonymisation is a
  safeguard against accidental disclosure, not a certificate that what leaves
  is anonymous in the sense a particular rule means it.

### Fixed

- Messages and documentation that still described the switch as opt-out: the
  `--enabled` flag advertised itself as the default; `pulse-ep-mcp` told an
  operator to *remove* the setting in order to allow access, which now denies
  it; the error raised against a refusing server named `PULSE_EP_MCP_ENABLED=0`
  as the cause when the variable is simply unset; the CLI reference listed no
  `--enabled` row at all; and the MCP guide's configuration table never
  mentioned the variable that governs all of it.

## [0.3.1] — 2026-09-07

A documentation release. 0.3.0 changed what the project *is* — a fourth
surface, a role the server enforces, a one-command setup — and the two files
a reader meets first still described the one before it.

### Fixed

- **`README.md` and `ARCHITECTURE.md` described the 0.2 project.** Both listed
  three surfaces where there are now four, a console-script list without
  `pulse-ep-init` and `pulse-ep-mcp`, and a top-level `alembic/` directory that
  stopped existing when the migrations moved into the package — so the
  documented way to create the schema pointed at a path an installed
  deployment does not have. The quickstart still walked through the six manual
  steps `pulse-ep-init` now does in one, the extras list omitted `[mcp]`, and
  neither file mentioned that signal traces are imported at all, let alone that
  they are opt-in because they dwarf the rest of an export.
- `ARCHITECTURE.md` claimed `conftest.py` and the synthetic demo are the only
  places that generate test input; a test needing a particular shape — a folded
  surface, a mesh with a reordered colour section — builds one inline. It also
  now writes down two design decisions that existed only in the code: roles are
  enforced rather than annotated, and what leaves a deployment towards an AI
  client is the operator's decision, not a tool's.
- A stray changelog line, appended below the 0.1.0 notes when the 0.3.0 entry
  was assembled, duplicated the half-open surface-area bins already described
  under 0.3.0.

## [0.3.0] — 2026-09-07

### Security

- **`/register_user` had no authentication and took the role from the request
  body**, so anyone who could reach a deployment could ask for `role: admin`
  and get it. The REST reference has always described the endpoint as admin
  only. Registration stays open — the bundled UI has a page for it — but an
  unauthenticated caller may now only ever create a plain `user`; naming a
  privileged role requires an administrator's token.
- **The `role` claim was minted at login and never read again.** The four
  endpoints documented as admin-only were open to every account, and the
  read-only user the MCP guide recommends could set map attributes and delete
  colormaps and reports. Three roles are enforced now — `admin`, `user`, and
  `readonly`, refused on every endpoint that changes stored state, which is
  what makes a read-only MCP account a property of the deployment rather than
  a sentence in a document. Reads that arrive as `POST` (a filter, an area
  integration, a comparison) stay open. An account whose role claim predates
  this is treated as an ordinary user: nobody is locked out, nobody promoted.

### Added

- **`pulse-ep-init`** brings a fresh installation to a running state in one
  command: it writes `.env` with a generated JWT secret, creates the waveform
  and drop directories, applies the migrations, seeds the colormaps, creates
  an administrator and, on request, a `readonly` account for the MCP server —
  printing the client configuration to paste. The quickstart was fifteen
  commands, and the ones easiest to miss are the ones whose absence looks like
  a different bug. Interactive where there is a terminal, flags and defaults
  otherwise, and idempotent: an existing `.env` is kept, migrations run only
  when behind, and an account that exists is left alone with its password
  unchanged — never reported as though a new one had been set.
- **MCP access can be switched off** (`PULSE_EP_MCP_ENABLED=0`), at both ends
  with one setting: the server refuses requests that identify themselves as
  MCP (`403`, other clients untouched), and `pulse-ep-mcp` refuses to start.
  Until now that decision lived only with whoever started the MCP server; a
  deployment had no say. The MCP identifies itself on every request
  (`X-Pulse-EP-Client`), which also makes AI access visible in the server log —
  a gate against a forgotten or misconfigured MCP, not against a person with
  valid credentials, for whom the boundary is the account.
- **An MCP server** (`pulse-ep-mcp`, `pip install "pulse-ep[mcp]"`): read-only
  access to a deployment for an AI client, as a fourth peer beside the REST
  API, the viewer and the toolkit — and a client of the same JWT endpoints,
  not a second route into the database. It answers what SQL on the database
  cannot: signal samples (which live outside it as Parquet), what a map's
  scalar fields mean and range over, and the operations that are computation
  rather than query. The complete stored data is reachable too — `fetch_map`,
  `fetch_points` and `fetch_waveform` write it next to the client and return
  the path, because one real map is 3.2 MB of JSON: in a file it can be
  computed with, in a context window it only fills it.
- **Study identity is anonymised by default** in MCP results. A study is named
  after its export, and a real one has the shape of this invented example —
  `10054321_XY_AB 01_02_2020 09-15-00` — a case number, initials and the time of the procedure — which is
  also embedded in stored file paths. The alias is the database id
  (`study/12`): no key file, no mapping table. Map names, quantities, units and
  signal values are untouched. `--no-anonymize` (or
  `PULSE_EP_MCP_ANONYMIZE=0`) switches it off for local work; no *tool* can,
  because a model must not be able to lift the restriction it is under. See
  [the MCP guide](guides/mcp.md).
- **`GET /epmaps/<id>/points`** and **`GET /epmaps/<id>/waveforms`** serve a
  map's points and its signal windows on their own. Both were only reachable
  through `/get_mesh_data?representation=raw`, which returns a whole mesh
  alongside — tens of thousands of vertices to read a few hundred
  measurements.
- **`waveform_from_parquet()`** reads a downloaded waveform back without a
  store around it — what every client of `/waveforms/<id>/download` otherwise
  has to reimplement.
- **A CARTO pace map's points carry their pace-match score.** CARTO writes the
  score per point exactly as it writes it per vertex — as the annotation
  difference `Map_Annotation - Reference_Annotation`, negative, with `-10000`
  on the reference beat that is never scored against itself — and the
  conversion labelled that difference `activation_time` on every map. So a
  pace map's points carried "activation times" of -50 … -100 ms, one of
  -10000, and the only per-site measurement of a pace map was invisible
  under that name; a client sampling the vertex field at the point instead
  got the vendor's interpolation, which differs from the point's own score
  by more than two points at 21 % of the points of a reference study.
  Points now follow the mesh's verdict (`point_primary_kind`): on a pace map
  the difference is `pacemap_score` (%), sentinels and non-percentages are
  omitted, on an activation map it stays `activation_time`. Verified against
  the `_car.txt` of 59 pace maps: 2987 of 3021 points identical, the rest
  correctly missing. An export that writes the scores unsigned is still
  classified an activation map — the `pacemap` attribute remains the override.
  The mesh's verdict is read from the **column** the points correspond to: a
  scalar field records which CARTO column it came from (`carto:LAT`,
  `carto:Paso`), so an activation map whose export also fills `Paso` — now
  possible, since colour columns are read by name — keeps activation times on
  its points instead of having them read as percentages.
- **Measurement points carry their annotation components**
  (`MeasurementPoint.annotations`, `measurement_points.annotations`, migration
  `f3a8b5c6d201`): the window's first sample on the study clock, the reference
  and mapping annotations as offsets into it, and the window of interest —
  what says where in a 2.5 s signal window a point's beat sits. Only the
  *derived* value (the activation time or pace-match score) had survived into
  the vendor-neutral point; the components lived on in CARTO's fixed-column
  `ep_map_points`, which only `pulse-ep-import-carto` writes, so a study
  imported through the drop directory had them nowhere. A stored waveform
  records the same facts under the same names, so a point and its window now
  agree by construction rather than by coincidence.
- **`pulse-ep-import-carto` built its measurement-point rows by hand**, so
  every field added to the point since — `tags`, and now `annotations` —
  reached the database on the queue path and was silently null on the CLI one.
  Both paths go through `measurement_points_to_models` now and produce
  identical rows.
- **Measurement points carry their tags** (`MeasurementPoint.tags`,
  `measurement_points.tags`, migration `d7e2c4a9f1b6`): the names of the
  markers the study catalogue put on the point — `Location Only` on the
  reference beat of a pace map, `Scar`, `His`, a study's own labels —
  resolved through the study's `TagsTable`. The catalogue's element text had
  been discarded by a stub (`xml_proc.str2var` returned `None` for every
  non-empty string), which is why `<Tags>` looked empty in every parsed
  study.

- **CARTO signals are imported.** Every acquired point has a
  `*_ECG_Export_*.txt` — 2.5 s of all 78 channels at 1 kHz — and none of them
  were ever read; the note in the code said "too large for DB storage", which
  was true of the relational database and not of the Parquet waveform store
  that has existed since. Opt-in (`pulse-ep-import-carto --waveforms
  --store-dir …`, or the waveform selection in the import plan), converted to
  millivolts, timestamped on the study clock, and stored with the points taken
  from that window and the channels each of them was annotated on. A
  multi-electrode catheter acquires many points from one recording — in the
  reference export 1934 points share 699 windows — so the samples are stored
  once and every point references that copy. About 20× smaller as Parquet than
  as the exported text.
- **`interpolate_scalar_values(method=…)`** — the method only ever masked the
  vendor's own per-vertex field. It can now compute the field from the map's
  measurement points instead: `gaussian` (straight-line distance) or
  `geodesic` (along the surface, via the heat kernel — two sparse solves, not
  one distance field per point). `cycle_length` interpolates activation times
  cyclically, so late meets early instead of averaging straight through a
  reentrant wavefront. The default stays `mask`; see
  [Masking and interpolation](guides/interpolation.md).
- **`pulse-ep-migrate`**, and the migrations now ship inside the package.
  `alembic upgrade head` only ever worked from a source checkout — an
  installed deployment had no way to run them, which the promise that
  existing databases keep working across releases depends on.

### Fixed

- **A histogram's top bin dropped its maximum.** Adjacent bins stopped
  counting a boundary value twice — `area_of_range` is half-open, as the REST
  reference always said — and every caller moved to the new rule except
  `plot_histogram`, whose highest bin then lost every vertex sitting exactly
  at the top of the range. On a three-value sample the bins summed to two
  thirds of the surface, and the third that vanished was the perfect pace
  match.
- **Re-seeding a colormap corrected only one of its display flags.**
  `pulse-ep-populate-colormaps` learned to bring `is_relative` in step with a
  changed definition but left `clipping` and `use_gradient` at whatever the
  database was first seeded with — so `viridis_0_3_mV`, whose fixed 0–3 mV
  scale depends on clipping being on, would have kept the wrong setting on any
  database seeded before it existed. All three are synced now; colours and
  intervals still stay as the operator edited them. A definition carrying
  annotations but no intervals now reports which colormap is wrong instead of
  failing inside `len(None)`.
- **The CARTO mesh reader took its per-vertex columns by position.** A `.mesh`
  file names its own columns, and only three of them were read: `Paso` (the
  pace-match score), `µBi` and the entire `[VerticesAttributesSection]`
  (`SCAR`, `EML`) never arrived, and an export ordering the columns
  differently would have had every quantity mislabelled without a word.
  Columns are now taken by name, unknown ones import under their raw CARTO
  token, and empty ones — most of the thirteen, in any given export — are not
  registered at all.
- **The cross-language examples worked for CARTO only.** ParaView, R, MATLAB
  and the Jupyter notebook all defaulted to `scalar_name = "act"` — a
  CARTO-only name that every EnSiteX map rejects, so the ParaView exporter
  failed with `Unsupported scalar_name: act` on exactly the vendor 0.2.0 was
  released for. They now omit the name and take the map's own primary
  quantity.

### Added

- `/get_mesh_data` echoes the `scalar_name` it used, so a client that omits
  the parameter can tell what it received.

## [0.2.1] — 2026-09-06

Everything here was found by installing 0.2.0 from its published tag into a
clean directory and walking through the documented setup against real
exports. None of it was visible in a working copy, and none of it was caught
by the test suite — the gap was that nothing exercised the *installed*
package or the viewer end to end.

### Fixed

- **EnSiteX maps could not be displayed in the viewer at all.** The mesh
  endpoint projected measurement positions from the legacy CARTO `xyz`
  array, which EnSiteX imports never populate, so every EnSiteX map failed
  with `self.xyz must be defined`. Positions now fall back to the
  vendor-neutral measurement points, and a map with no measurements at all —
  a DIF mesh carrying only per-vertex fields — renders unmasked instead of
  failing.
- **A reload stacked meshes instead of replacing them.** The scene was
  cleared only on a first load, so changing the datatype, colormap or
  distance added another mesh on top of the previous one. Clearing now also
  keeps the scene's lights (it used to remove them) and disposes geometries
  and materials, which a 50k-vertex mesh reloaded on every change otherwise
  leaks.
- The viewer sent the literal string `"null"` as `scalar_name` when no
  quantity had been chosen yet; the parameter is now omitted so the server
  resolves the map's primary quantity.
- The datatype selector was populated by a function that was never called,
  leaving it empty after the hardcoded ACT / VOL options were removed.
- **`pulse-ep-import-carto` produced studies the rest of the platform could
  not recognise.** The CLI has its own import loop, and it never set
  `vendor`, never wrote vendor-neutral `measurement_points` (only the legacy
  fixed-column rows), and reported every per-point XML as a failed study —
  ~1946 warnings on a real export, and never wrote `scalar_fields` either —
  so a CARTO map reached the viewer with no quantities to offer at all. A
  CARTO study imported the documented way therefore could not be compared
  with an EnSiteX one, which is the point of 0.2.0.
- Study names began with the literal `"None-"` when an export sat in a path
  too shallow for the distinguishing component; the name now falls back to
  the study's own name.
- **Three console scripts were broken once installed.**
  `pulse-ep-populate-colormaps` pointed at a `main` that did not exist;
  `pulse-ep-extract-meshes` ran its whole body at import time, so it
  demanded a database connection merely to be imported, and had no `main`
  either; `pulse-ep-tag-maps` parsed `sys.argv` at import, which made
  argparse read *the importing program's* arguments and call `sys.exit(2)`.
  A test now checks every declared entry point.
- **A fresh install failed on Python 3.13 and 3.14.** Five dependencies were
  capped below their current major (`pyarrow<21`, `pillow<12`, `lxml<6`,
  `trimesh<5`, `pandas<3`), and newer Pythons only get wheels for recent
  releases — so pip fell back to building pyarrow from source and failed,
  while `requires-python` still advertised `>=3.10` with no upper bound. The
  caps now admit the current major of each dependency.

### Changed

- The CI matrix covers Python 3.10 through 3.14 (was 3.10–3.12), so the
  supported range is actually tested.

## [0.2.0] — 2026-09-06

First multivendor release: CARTO 3 and EnSiteX are peers, storing values
under one vendor-neutral vocabulary so a single query spans both.

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
- **7-Zip import support.** CARTO exports are frequently 7-Zip archives
  named `.zip`; the container is detected by content signature, so such an
  export imports without renaming. Needs the optional `pulse-ep[sevenzip]`
  extra.
- **VisiTag ablation sites** are read into study-level placed points, with
  RF parameters (duration, force, FTI, impedance drop, RF/ablation index).
  **The parser is unverified** — no real VisiTag export was available to
  test against — so it matches columns by name rather than position and
  yields no points at all when the columns are unrecognisable. The import
  plan flags any VisiTag file with that warning.
- `docs/` — a full mkdocs-material documentation site, deployed via
  GitLab Pages.
- `ARCHITECTURE.md` — internal engineering documentation (module
  layout, design decisions, quality gate).
- Cross-language [examples](examples/index.md) for ParaView, R, MATLAB
  and Jupyter — each computing the per-vertex scalar histogram and the
  per-interval surface-area breakdown from the same REST payload.

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
- `examples/` is now positioned as the cross-language reproducibility
  statement of the accompanying software paper.

### Fixed

- `CartoImporter.parse` raised unconditionally when no map filter was
  given, so every registry- and queue-driven CARTO import failed.
- The import queue crashed on CARTO bundles, because it called
  `prepare`/`commit` — which only EnSiteX implements — without a fallback.
- EnSiteX bi/uni map pairs were split by a case difference in the filename
  and by an export typo (`-bpolar`), planning four map runs as six.
- `difNNN.xml`, the largest file in an EnSiteX export, was ignored: it
  holds the CT segmentation (endocardium, wall-thickness shells, channels,
  fat infiltration).
- Seven of eight EnSiteX DxL channels were dropped; all are read now.
- EnSiteX `adjTime` was recorded as `activation_time` although it is the
  annotation window offset, often constant across an entire export.
  Activation time now comes from the `LAT` channel.
- CARTO `prepare` reported every per-point XML in an export as a failed
  study catalogue, producing ~2000 spurious issues on a real export.
- The `ruff` version was specified three different ways, so CI
  format-checked with a different formatter than contributors ran.
- The data-model reference documented a schema that no longer existed.

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
