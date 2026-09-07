# Command-line tools

Commands are installed with the package. Run them from the configured
environment; database operations use `PULSE_EP_*` settings.

| Command | Purpose |
| --- | --- |
| `pulse-ep-init` | Configure a local installation, migrate, seed and create accounts |
| `pulse-ep-migrate` | Apply or inspect database migrations |
| `pulse-ep-import-carto` | Import CARTO studies from a directory or archive |
| `pulse-ep-import-ensite` | Import an EnSite X directory or archive |
| `pulse-ep-server` | Start the local Flask service and viewer |
| `pulse-ep-populate-colormaps` | Seed and synchronise default colormap flags |
| `pulse-ep-create-user` | Create or update a user's password and role |
| `pulse-ep-tag-maps` | Preview or apply heuristic map attributes |
| `pulse-ep-check-mesh` | Inspect the structure of a mesh response over REST |
| `pulse-ep-extract-meshes` | Export stored geometry to NPZ |
| `pulse-ep-demo` | Run an in-memory synthetic example |
| `pulse-ep-mcp` | Serve read-only MCP tools over stdio |

Commands with arguments provide `--help`. The service and colormap seeder
are started without arguments.

## `pulse-ep-init`

```bash
pulse-ep-init
pulse-ep-init --non-interactive --admin-user admin
```

The initializer writes `.env`, creates waveform/drop directories, tests the
database connection, applies migrations, seeds colormaps and creates an
administrator. Existing accounts retain their passwords and roles.

| Option | Purpose |
| --- | --- |
| `--env-file PATH` | Configuration file, default `.env` |
| `--database-url URL` | PostgreSQL connection; defaults to the environment or local Compose database |
| `--waveform-dir PATH`, `--drop-dir PATH` | Data directories |
| `--admin-user NAME`, `--admin-password VALUE` | Initial administrator; missing password is prompted for or generated |
| `--mcp`, `--no-mcp` | Explicitly request MCP on or off for a new configuration |
| `--mcp-user NAME`, `--mcp-password VALUE` | Read-only account when MCP is enabled |
| `--base-url URL` | Service URL for generated MCP client settings |
| `--non-interactive` | Use arguments and defaults without prompts |

MCP is disabled by default. Review institutional rules before enabling it.
An existing `.env` retains its values unless replacement is explicitly chosen;
missing setup fields are appended. Process environment values take precedence.
For Docker setup, use the commands in the [deployment guide](../guides/docker-deployment.md).

## `pulse-ep-migrate`

```bash
pulse-ep-migrate
pulse-ep-migrate --current
pulse-ep-migrate --revision head --sql
```

The default target is `head`. `--current` displays the current revision;
`--sql` emits migration SQL without applying it. Migrations ship with the
installed package. From a source checkout, `alembic upgrade head` is an
alternative. Server startup creates missing tables but does not upgrade
existing columns; run migrations after an upgrade.

## `pulse-ep-import-carto`

```bash
pulse-ep-import-carto -i /path/to/export.zip --dry-run
pulse-ep-import-carto -i /path/to/export.zip
```

| Option | Default | Purpose |
| --- | --- | --- |
| `-i`, `--input PATH` | required | Directory tree, ZIP or 7-Zip archive |
| `--pattern GLOB` | `*.xml` | Study-manifest discovery pattern |
| `--no-recursive` | off | Restrict discovery to the root directory |
| `--map-filter REGEX` | `.*` | Case-insensitive map-name filter |
| `--dry-run` | off | Inspect discovered studies and maps without database writes |
| `--progress` | off | Compact progress output |
| `--waveforms` | off | Import ECG windows |
| `--store-dir PATH` | unset | Required with `--waveforms` |
| `--clear` | off | **Erase and recreate the application schema before import** |

7-Zip input requires the `sevenzip` extra. Repeated ordinary imports skip
existing maps in the matching study; they do not update those maps in place.
Study identity includes source path context; unpack once into a fixed directory
for repeated imports. `--clear` also removes users,
reports and other studies; it is not a single-study replacement option.
See [CARTO import](../guides/carto-import.md).

## `pulse-ep-import-ensite`

```bash
pulse-ep-import-ensite -i /path/to/export.zip --dry-run
pulse-ep-import-ensite -i /path/to/export.zip
```

Supports `-i`/`--input`, `--dry-run`, `--clear`, `--waveforms` and
`--store-dir`. Input is a directory or archive. A dry run prints the import
plan. Existing studies are skipped by export identity; **EnSite X's `--clear`
replaces that study**, unlike CARTO's database-wide reset. Stored Parquet files
are not automatically deleted when reference rows are removed.
See [EnSite X import](../guides/ensite-import.md).

## `pulse-ep-server`

```bash
pulse-ep-server
```

Starts Flask with `PULSE_EP_HOST`, `PULSE_EP_PORT` and `PULSE_EP_DEBUG`.
The default URL is `http://127.0.0.1:5000`. For a deployed service, use a WSGI
runner such as the gunicorn command in the supplied Dockerfile after applying
migrations. A direct gunicorn invocation needs its own bind/worker arguments.

## `pulse-ep-populate-colormaps`

```bash
pulse-ep-populate-colormaps
```

Seeds eight presets: `viridis_0_3_mV`, `jet`, `viridis`, `plasma`, `magma`,
`inferno`, `pacemapping_5` and `pacemapping`. Existing names keep their colours
and intervals; `is_relative`, `clipping` and `use_gradient` are synchronised
with the shipped definitions. Requires an initialised database.

## `pulse-ep-create-user`

```bash
pulse-ep-create-user --username NAME --role readonly
pulse-ep-create-user --username NAME --role user --password-stdin
```

The role is `admin`, `user` or `readonly`, default **admin**. A password is
prompted for unless `--password` or `--password-stdin` is provided. Existing
usernames are updated, including password and role. See [Managing users](../guides/managing-users.md).

## `pulse-ep-tag-maps`

```bash
pulse-ep-tag-maps --study "Synthetic"                 # preview
pulse-ep-tag-maps --study "Synthetic" --apply         # write attributes
pulse-ep-tag-maps --skip-existing --apply
```

Uses map names, legacy CARTO values and study-specific coordinate heuristics
to propose `atrium`, `part`, `type` and `pacemap` attributes. Review the dry-run
output: these rules originate in the development dataset and are not a
validated anatomical classifier. `--study` filters study names by substring;
`--skip-existing` skips maps with non-empty attribute dictionaries. For exact
attributes on selected IDs, use the administrator-only
[`/epmaps/set_attributes`](rest-api.md#post-epmapsset_attributes) endpoint.

## `pulse-ep-check-mesh`

```bash
pulse-ep-check-mesh --map-id 12 --representation raw
```

Uses `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME` and `PULSE_EP_PASSWORD`.
A missing password is prompted for. Options include `--base-url`, `--username`,
`--scalar-name`, `--distance` (default 5 mm) and `--representation` (`raw` or
`display`, default `raw`). Prints response structure, mesh size and available
field names without printing credentials, tokens or individual measurements.
This is an API diagnostic, not a mesh-topology quality assessment.

## `pulse-ep-extract-meshes`

```bash
pulse-ep-extract-meshes --maps 12 13 --output /tmp/extracted
```

Requires database access. Writes `mesh_012.npz` and `mesh_013.npz` with the
keys `vertices` and `triangles` only. `--maps` (`-m`) is required; `--output`
(`-o`) defaults to `./decay_profiles` or `PULSE_DECAY_DIR`. For complete fields,
points and metadata, use the raw REST export instead.

## `pulse-ep-demo`

```bash
pulse-ep-demo --resolution 24 --sigma 6 --noise 0.02
```

Creates a synthetic ellipsoid (530 vertices, 1,056 triangles at the default
resolution), a Gaussian score field and an `EPMap`, then prints its summary
and interval areas. No database is used. `--show` opens a PyVista window.

## `pulse-ep-mcp`

```bash
pulse-ep-mcp --check
pulse-ep-mcp
```

Requires the `mcp` extra. Credentials come from `PULSE_EP_MCP_TOKEN` or
`PULSE_EP_MCP_USERNAME`/`PULSE_EP_MCP_PASSWORD`. Set `PULSE_EP_MCP_ENABLED=1`
on the service and in the MCP process only after reviewing institutional rules.
The local process reads its settings from process environment variables;
a service `.env` file is not automatically loaded by this command.

Options: `--base-url`, `--download-dir`, `--anonymize`/`--no-anonymize`,
`--enabled`/`--disabled`, and `--check`. Local enable flags cannot override a
service that refuses MCP. `--check` checks connection and visible studies;
it exits 2 on a configuration problem and 3 when the service refuses MCP.
See the [MCP guide](../guides/mcp.md) for setup and tool definitions.
