# Command-line tools

pulse-ep installs eight console scripts. They are the primary
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
pulse-ep-demo [--resolution 16] [--sigma 6.0]
```

Self-contained synthetic walkthrough — builds an icosphere atrial mesh,
injects a Gaussian score field, ingests it into an in-memory SQLite
through the full ORM stack, and prints per-interval areas. No
PostgreSQL required.

The defaults reproduce the smoke-test configuration used in CI.

## `pulse-ep-import-carto`

```bash
pulse-ep-import-carto -i <DIR> [--map-filter REGEX] [--dry-run] [--progress]
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
