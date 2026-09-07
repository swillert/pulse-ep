# Command-line tools

pulse-ep installs a set of console scripts. They are the primary
admin / scripted-ops surface; everything they do is also accessible
through the [Python API](python-api.md).

| Script                                                           | Subsystem                                       |
| ---------------------------------------------------------------- | ----------------------------------------------- |
| [`pulse-ep-server`](#pulse-ep-server)                            | Run the Flask REST API + viewer.                |
| [`pulse-ep-demo`](#pulse-ep-demo)                                | Run the synthetic end-to-end walkthrough.       |
| [`pulse-ep-import-carto`](#pulse-ep-import-carto)                | Import a CARTO 3 export.                        |
| [`pulse-ep-tag-maps`](#pulse-ep-tag-maps)                        | Set the `pacemap` (or other) attribute.         |
| [`pulse-ep-populate-colormaps`](#pulse-ep-populate-colormaps)    | Seed the default colormaps.                     |
| [`pulse-ep-create-user`](#pulse-ep-create-user)                  | Create a user.                                  |
| [`pulse-ep-check-mesh`](#pulse-ep-check-mesh)                    | Mesh quality / topology check.                  |
| [`pulse-ep-extract-meshes`](#pulse-ep-extract-meshes)            | Dump meshes as NPZ for offline analysis.        |
| [`pulse-ep-mcp`](#pulse-ep-mcp)                                  | MCP server: read-only access for an AI client.  |
| [`pulse-ep-init`](#pulse-ep-init)                                | Configure a fresh installation and bring it up. |

All scripts accept `--help` for full flag listings. Where a flag is
omitted below it is either obvious from the name or covered in the
[Quickstart](../getting-started/quickstart.md) /
[guides](../guides/carto-import.md).

## `pulse-ep-server`

Run the Flask app on the configured host and port.

```bash
pulse-ep-server
```

Reads `PULSE_EP_HOST` / `PULSE_EP_PORT` / `PULSE_EP_DEBUG` from
[`Settings`][pulse_ep.core.config.Settings]. `init_db()` is called once at
startup, so first-run schema creation is implicit.

For production use `gunicorn pulse_ep.server.app:app` directly with
your preferred worker count. The bundled `Dockerfile` does exactly
that.

## `pulse-ep-demo`

```bash
pulse-ep-demo [--resolution 24] [--sigma 6.0] [--noise 0.02] [--show]
```

Self-contained synthetic walkthrough — builds an atrium-like ellipsoid
(half-axes 25 / 25 / 35 mm), paints a Gaussian pace-mapping score field onto
it, wraps it as an `EPMap` and prints the mesh size, the score distribution,
the total surface area and the area per score interval.

| Flag | Default | Notes |
| ---- | ------- | ----- |
| `--resolution` | `24` | Theta/phi resolution of the sphere it starts from; `24` gives 530 vertices and 1056 triangles. |
| `--sigma` | `6.0` | Width of the Gaussian score field, in millimetres. |
| `--noise` | `0.02` | Relative standard deviation of the noise added to the scores. |
| `--show` | off | Open an interactive 3D viewer on the result (PyVista). |

**It uses no database** — not PostgreSQL, and nothing embedded either. Nothing
is persisted and nothing is read back; it exercises the array-only public API,
which is what makes it a first check that an installation is healthy.

## `pulse-ep-migrate`

```bash
pulse-ep-migrate [--revision REV] [--current] [--sql]
```

Bring the configured database up to the current schema. The migration
scripts ship inside the package, so this works from a plain `pip install`
as well as from a checkout — `alembic upgrade head` only works in a
checkout, where `alembic.ini` exists.

| Flag         | Default | Notes                                                  |
| ------------ | ------- | ------------------------------------------------------ |
| `--revision` | `head`  | Target revision; `head` is the newest.                 |
| `--current`  | off     | Report the database's current revision and exit.       |
| `--sql`      | off     | Print the SQL instead of executing it (offline mode).  |

## `pulse-ep-init`

```bash
pulse-ep-init [--non-interactive] [--database-url URL] [--admin-user NAME]
              [--mcp-user NAME] [--mcp | --no-mcp] [--env-file PATH]
```

Brings a fresh installation to a running state: writes `.env` with a
generated JWT secret, creates the waveform and drop directories, applies the
migrations, seeds the colormaps, creates an administrator and — with
`--mcp-user` — a `readonly` account for the MCP server, printing the client
configuration block to paste.

| Flag | Default | Notes |
| ---- | ------- | ----- |
| `--non-interactive` | off | Ask nothing; flags and defaults only, generating what is missing. |
| `--database-url` | `postgresql://pulse:pulse@localhost:5432/pulse` | Tested before anything is written to it. |
| `--admin-user` / `--admin-password` | asked | The password is generated and printed once when omitted. |
| `--mcp-user` / `--mcp-password` | asked | A `readonly` account; its password goes into the client block, not into `.env`. |
| `--base-url` | `http://127.0.0.1:5000` | How the MCP server reaches this deployment. |
| `--env-file` | `.env` | An existing file is kept unless you say otherwise (a backup is made). |

Idempotent: an existing `.env` is kept, migrations are applied only when
behind, and an account that exists is left alone — with its password
unchanged, and never reported as if it had been reset.

## `pulse-ep-import-carto`

```bash
pulse-ep-import-carto -i <DIR> [--map-filter REGEX] [--dry-run] [--progress]
                      [--waveforms --store-dir DIR]
```

Import CARTO studies from a directory tree, discovering study XML files
within it.

| Flag            | Default | Notes                                                            |
| --------------- | ------- | ---------------------------------------------------------------- |
| `-i`, `--input` |         | Required. **A directory** — extract an archive first.            |
| `--pattern`     | `*.xml` | Glob for study XML files.                                        |
| `--no-recursive`| off     | Do not descend into subdirectories.                              |
| `--map-filter`  | `.*`    | Case-insensitive regex over map names.                           |
| `--dry-run`     | off     | Discover and parse, write nothing.                               |
| `--progress`    | off     | Compact one-line progress display.                               |
| `--waveforms`   | off     | Also import the per-point ECG windows. One 2.5 s window of every channel per acquired point — gigabytes on a real study. |
| `--store-dir`   |         | Where to write Parquet waveforms. Required together with `--waveforms`. |
| `--clear`       | off     | ⚠️ **Drops and recreates every table** before importing — this is not "reimport this study", it empties the database. |

!!! warning "`--clear` means something different here than in `pulse-ep-import-ensite`"

    On the EnSiteX importer, `--clear` removes *the one study* being
    reimported. On this one it drops the **entire schema**. Do not reach for
    it out of habit.

This command takes a directory, while the vendor-detecting pipeline
(`ImportSource`) also accepts ZIP and 7-Zip archives. To import an archived
CARTO export with this CLI, unpack it first:

```bash
# ZIP
unzip -q export.zip -d /tmp/carto-export

# 7-Zip — CARTO often writes these, misleadingly named .zip
python -c "import py7zr; py7zr.SevenZipFile('export.zip').extractall('/tmp/carto-export')"
```

See the [CARTO import guide](../guides/carto-import.md) for export-format
details and troubleshooting.

## `pulse-ep-import-ensite`

```bash
pulse-ep-import-ensite -i <PATH> [--dry-run] [--clear]
                       [--waveforms --store-dir DIR]
```

Import an Abbott EnSiteX (St. Jude) export from a ZIP archive or an
unpacked directory.

| Flag           | Default | Notes                                                                    |
| -------------- | ------- | ------------------------------------------------------------------------ |
| `-i, --input`  |         | Required. ZIP archive or directory.                                      |
| `--dry-run`    | off     | Print the import plan and exit. Writes nothing.                          |
| `--clear`      | off     | Re-import a study that is already present (otherwise it is skipped).     |
| `--waveforms`  | off     | Also import signal traces. They can dwarf the rest of the export.        |
| `--store-dir`  |         | Where to write Parquet waveforms. Required together with `--waveforms`.  |

Imports are idempotent by the export's study GUID. Run `--dry-run` first
on an export from an unfamiliar site — it lists the detected maps, their
vertex counts, the quantities each carries and any issues found.

See the [EnSiteX import guide](../guides/ensite-import.md).

## `pulse-ep-tag-maps`

```bash
pulse-ep-tag-maps [--pacemap ID...] [--list] [--clear ID...]
```

Set or clear the `pacemap` boolean on a list of map IDs. Useful right
after import.

```bash
# Mark maps 12, 13, 14, 15 as pace-maps
pulse-ep-tag-maps --pacemap 12 13 14 15

# Print the current pacemap flag for every map
pulse-ep-tag-maps --list
```

Generic attributes are settable through the
[`/epmaps/set_attributes`](rest-api.md#post-epmapsset_attributes) REST
endpoint.

## `pulse-ep-populate-colormaps`

```bash
pulse-ep-populate-colormaps
```

Seed the database with three default colormaps appropriate for
pace-mapping similarity, activation time and bipolar voltage. Idempotent:
re-running is safe; existing colormaps with the same `name` are skipped.

## `pulse-ep-create-user`

```bash
pulse-ep-create-user --username NAME --role {admin,user}
                     [--password PWD | --password-stdin]
```

Create a user. Passwords are stored as bcrypt hashes (cost factor from
`PULSE_EP_BCRYPT_LOG_ROUNDS`, default 12). If neither `--password`
flag is given, the script prompts interactively with hidden input.

| Flag                | Notes                                                       |
| ------------------- | ----------------------------------------------------------- |
| `--username`        | Required. Must be unique.                                   |
| `--role`            | Required. `admin` or `user`.                                |
| `--password`        | Inline password. Insecure for shell history, fine for tests. |
| `--password-stdin`  | Reads the password from stdin. Recommended for CI / secret managers. |

See [Managing users](../guides/managing-users.md) for the full role
model and password-rotation recipes.

## `pulse-ep-check-mesh`

```bash
pulse-ep-check-mesh [--study NAME] [--map-id ID]
```

Mesh quality / topology check on imported maps. Reports vertex /
triangle counts, non-manifold edges, isolated vertices and duplicate
faces. Useful to triage unexpected viewer rendering issues.

## `pulse-ep-extract-meshes`

```bash
pulse-ep-extract-meshes --output DIR [--study NAME] [--map-id ID]
```

Dump each EPMap as a NumPy NPZ file with keys `vertices`, `triangles`,
`scores`, `point_coordinates`, `point_scores`. Useful for external
scientific pipelines that consume raw arrays — e.g. when you want to
hand a dataset to an external collaborator without giving them
PostgreSQL access.

```bash
pulse-ep-extract-meshes --study "AF-2024-01" --output /tmp/extracted/
# /tmp/extracted/AF-2024-01_LA-pacemap-001.npz
# /tmp/extracted/AF-2024-01_LA-pacemap-002.npz
# …
```

## `pulse-ep-mcp`

```bash
pulse-ep-mcp [--base-url URL] [--download-dir DIR]
             [--anonymize | --no-anonymize] [--enabled | --disabled] [--check]
```

Serves a pulse-ep deployment to an MCP client (Claude Desktop, Claude Code, …)
over stdio, **read-only**. Needs the optional extra: `pip install "pulse-ep[mcp]"`.

| Flag | Default | Notes |
| ---- | ------- | ----- |
| `--base-url` | `PULSE_EP_MCP_BASE_URL`, else `http://localhost:5000` | The pulse-ep server it is a client of. |
| `--anonymize` | on | Study names become `study/<id>`; paths and free-text fields are redacted. |
| `--no-anonymize` | | Send real study names — they carry case numbers and initials. Warns on stderr. |
| `--download-dir` | `PULSE_EP_MCP_DOWNLOAD_DIR`, else a temp folder | Where `fetch_map` / `fetch_points` / `fetch_waveform` write bulk data. |
| `--enabled` | | Serve for this run. AI access is **off unless** `PULSE_EP_MCP_ENABLED=1`; the flag sets it for one run and cannot make a deployment serve. |
| `--disabled` | on | Do not serve — the default, and what any unset or unrecognised `PULSE_EP_MCP_ENABLED` means. Prints why and exits 0: not serving on purpose is not a crash. |
| `--check` | off | Connect, log in, print what the model would see, exit. Exit 2 on a configuration problem, **3** when the deployment refuses MCP access. |

Credentials come from `PULSE_EP_MCP_TOKEN`, or `PULSE_EP_MCP_USERNAME` +
`PULSE_EP_MCP_PASSWORD`. There is no tool that changes the anonymisation mode:
it is the operator's decision, taken at startup.

Enabling MCP access sends study data to a language model. Establish what your
data permits, and adapt what is sent where more is required, before switching
it on — see the [MCP guide](../guides/mcp.md#enabling-it).

See the [MCP guide](../guides/mcp.md) for the tool list and client setup.

## Common patterns

??? example "Daily import + report (cron)"

    ```bash
    #!/usr/bin/env bash
    set -euo pipefail

    export PULSE_EP_BASE_URL=http://internal.example/pulse-ep
    export PULSE_EP_DATABASE_URL=postgresql://…

    for export in /data/uksh/$(date +%Y-%m-%d)/*.zip; do
        pulse-ep-import-carto "$export" --on-conflict update
    done
    ```

??? example "Bulk-tag every pace-map matching a name pattern"

    ```python
    from pulse_ep import get_db_session, EPMapModel
    import subprocess, re

    with get_db_session() as s:
        ids = [m.id for m in s.query(EPMapModel).all()
               if re.match(r"^LA-pacemap-\d+$", m.map_name)]

    subprocess.run(
        ["pulse-ep-tag-maps", "--pacemap", *map(str, ids)],
        check=True,
    )
    ```

## See also

- [Python API reference](python-api.md) — the same functionality
  accessed programmatically.
- [REST API reference](rest-api.md) — the HTTP surface that the viewer
  uses; some CLI operations are also exposed there.
