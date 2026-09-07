# The MCP server

`pulse-ep-mcp` exposes a deployment to an AI client (Claude Desktop, Claude
Code, any MCP host) over the [Model Context
Protocol](https://modelcontextprotocol.io) — read-only, and with study
identity anonymised by default.

## What it is for

The tools combine data discovery, summaries, signal access and quantitative
operations through the existing service. Signal samples are stored in Parquet
outside PostgreSQL. Compact tools return summaries; bulk tools download
complete stored data for analysis in the MCP host's local environment.

It is a client of the same JWT REST API as the viewer and the `examples/`
clients — there is no privileged path into the database — so it sees exactly
what the account it logs in with can see.

## Enabling it

**MCP access is off until you turn it on.** It is not a default anyone
inherits, and it is not enabled by installing the extra.

!!! danger "Establish what you may send before you enable it"

    Serving MCP means study data leaves this deployment for a language model —
    in most setups a third-party service, outside the systems your data was
    approved for. Whether that is permitted is not a question this software
    can answer for you.

    Before turning it on, establish that it is allowed: your institution's
    rules on processing research and patient data, the terms and any ethics
    approval the studies were collected under, the data protection agreement
    with the AI provider, and whatever your data protection officer requires.

    Those conditions may demand more than this software does by default. What
    the anonymiser removes is documented under [Study
    identity](#study-identity) — study names, paths and free-text fields —
    while map names, quantities and measured values are sent unchanged. Where
    that is not sufficient for your data, **adapt what is sent** (extend the
    anonymiser, use a separate deployment containing only approved studies, or use an approved local model)
    before enabling it, rather than after.

    Anonymisation is a safeguard against accidental disclosure, not a
    certification that the result is anonymous in the sense your rules mean.

Then set it explicitly, at **both** ends:

```bash
PULSE_EP_MCP_ENABLED=1
```

- **On the server** it decides for the deployment. While it is unset,
  requests that identify themselves as MCP are refused with `403`; the
  viewer, the example clients and every other consumer are untouched.
- **In the MCP process** it decides for that process, which is what a
  workstation wants. Without it, `pulse-ep-mcp` refuses to start: it prints
  why on stderr and exits 0 — not serving on purpose is not a crash, and a
  client that restarts a "failed" server would otherwise fight the setting.

One setting, read at both ends, so a shared environment covers both with one
line. `--enabled` and `--disabled` override the environment for a single run
of the local process — neither can talk a deployment into serving, which is
the point of the server holding the decision too.

```console
$ pulse-ep-mcp --check                 # deployment does not serve it
pulse-ep-mcp: http://pulse-ep.local does not serve MCP access
              (PULSE_EP_MCP_ENABLED=1 is not set on the server)
$ echo $?
3
```

## Switching it off

Unset `PULSE_EP_MCP_ENABLED`, or set it to `0` — anything that is not
`1`/`true`/`yes`/`on` refuses access, so a typo leaves it off rather than on.
It takes effect at both ends on restart, and revoking the account (below) is
what ends access for good.

!!! warning "A gate, not a boundary"

    The MCP names itself in a request header, honestly. Anything it can do, a
    person holding the same credentials can do with `curl` — so the server
    switch stops a **forgotten, inherited or misconfigured** MCP, which is the
    case that actually happens. It does not stop someone who wants in.

    What does: the account. Give the MCP its own `readonly` user — a role the
    server enforces, refused on every endpoint that changes stored state —
    and revoke access according to the [account guide](managing-users.md#revoking-access).
    `pulse-ep-init --mcp --mcp-user mcp` creates that account for a new
    configuration. The client sends `X-Pulse-EP-Client: pulse-ep-mcp/<version>`;
    logging that header requires a suitable access-log configuration.

## Study identity

An imported study is named after its export. A real CARTO one has the shape
of this invented example

```
10054321_XY_AB 01_02_2020 09-15-00
```

a case number, initials and the time of the procedure. That is not something
to hand to a language model by accident, and the name is also embedded in
stored file paths, so replacing a single field would not be enough.

**Anonymisation is on by default.** With it on:

| | |
| --- | --- |
| A study is called | `study/<id>` — the database id, no key file, no mapping table to keep or lose |
| Names embedded in other strings | replaced wherever they appear |
| Paths, `operator`, `notes`, patient fields | `[redacted]` |
| Map names, quantities, units, values, signals | Generally retained; map names and arbitrary fields still require review for identifiers |
| Every answer | carries `"anonymized": true` |

Resolving an alias is one query on the machine that holds the data:

```sql
select name from studies where id = 12;
```

To turn it off — because you are working locally on your own study and want
the names — start the server with `--no-anonymize` or set
`PULSE_EP_MCP_ANONYMIZE=0`. It then warns on stderr, and every answer says
`"anonymized": false`.

!!! warning "Only the operator can switch it"

    There is deliberately **no tool** that turns anonymisation on or off, and
    no argument on any tool that does it either. It is decided when the
    server is started; a model must not be able to lift the restriction it is
    under. Anything other than an explicit `0`/`false`/`no`/`off` keeps it on,
    so a typo in the configuration cannot quietly expose a study.

## Setup

```bash
pip install -e ".[mcp]"
```

The server talks to a running `pulse-ep-server`, so configure where that is
and how to log in:

| Variable | Meaning |
| -------- | ------- |
| `PULSE_EP_MCP_ENABLED` | `1` serves at all — **off unless set**, at both ends (see [Enabling it](#enabling-it)) |
| `PULSE_EP_MCP_BASE_URL` | pulse-ep server (default `http://localhost:5000`) |
| `PULSE_EP_MCP_TOKEN` | a JWT, if you have one … |
| `PULSE_EP_MCP_USERNAME` / `PULSE_EP_MCP_PASSWORD` | … or an account to log in with — give it the `readonly` role |
| `PULSE_EP_MCP_ANONYMIZE` | `0` turns anonymisation off (default: on) |
| `PULSE_EP_MCP_TIMEOUT` | seconds per request (default 60) |
| `PULSE_EP_MCP_DOWNLOAD_DIR` | where `fetch_*` writes bulk data (default: system temp) |

Check the configuration before wiring it into a client — this connects, logs
in, and prints exactly what the model would see:

```bash
pulse-ep-mcp --check
```

```
connected to http://127.0.0.1:5099
anonymised: True
studies visible: 1
  study/1  (carto)
```

Then register it with your MCP client. For Claude Desktop
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pulse-ep": {
      "command": "/path/to/.venv/bin/pulse-ep-mcp",
      "env": {
        "PULSE_EP_MCP_ENABLED": "1",
        "PULSE_EP_MCP_BASE_URL": "http://127.0.0.1:5000",
        "PULSE_EP_MCP_USERNAME": "readonly",
        "PULSE_EP_MCP_PASSWORD": "…"
      }
    }
  }
}
```

For Claude Code, register the executable with `claude mcp add pulse-ep --
/path/to/.venv/bin/pulse-ep-mcp`. Launch Claude Code from an environment
containing the MCP settings above, including `PULSE_EP_MCP_ENABLED=1`.
The local MCP process reads process environment variables, not the service
`.env` automatically.

## The tools

All read-only. Import, tagging and deletion stay with the CLI and the review
UI, where a person is present.

| Tool | Answers |
| ---- | ------- |
| `list_studies` | Which studies exist (id, alias, vendor). |
| `list_maps(study_id)` | A study's maps, and how many points each really holds. |
| `map_summary(map_id)` | What the map measured: quantities, kinds, units, ranges, attributes. |
| `area_of_range(map_id, min, max, …)` | Surface area between two values — the low-voltage / scar-area question. |
| `compare_maps(a, b, scalar_name, metric)` | Difference statistics between two maps; `metric="geodesic"` measures along the surface. |
| `read_points(map_id, limit, offset)` | The acquisition points and their measurements, paged (`limit=0` = all). |
| `list_waveforms(map_id, limit, offset)` | Which signal windows were recorded (metadata only, paged). |
| `read_waveform(waveform_id, channels, start_ms, end_ms)` | One window: per-channel statistics and a decimated trace. |
| `fetch_map(map_id, …)` | **The complete map** — mesh, every scalar field, every point, the signal index — written as JSON. |
| `fetch_points(map_id, …)` | **Every point** as CSV: one row per point, one column per quantity, plus its `annotation_*` components and tags. |
| `fetch_waveform(waveform_id, …)` | **The full window** as the stored Parquet: every channel, every sample. |

## Everything is reachable — but bulk goes to a file

The `fetch_*` tools write data under `PULSE_EP_MCP_DOWNLOAD_DIR` (default:
`pulse-ep-mcp` in the system temporary directory) and return a local path.
The MCP host needs file access and code execution to analyse these downloads;
the language model itself does not execute calculations merely by receiving
a path. `fetch_map(inline=True)` can return the full map directly when needed.

Filenames are reduced to basenames and downloaded metadata is passed through
the same configured redaction process as tool responses. Numerical data remain
sensitive where institutional rules say so. File download alone does not
transmit the full file to a model provider, but later host actions may do so.

`read_points` defaults to 200 points (`limit=0` means all); `list_waveforms`
defaults to 25 rows and uses a positive limit. `read_waveform` defaults to at
most 400 returned samples per selected channel, while its statistics use every
finite sample in the requested interval.

### The remaining limits

- **`compare_maps` never fetches the per-vertex delta** — statistics only.
  Fetch both maps if you want to compute your own.
- **`read_waveform` decimates the trace, but computes statistics over every
  sample**, so a peak that falls between two returned samples is still
  reported. Without `channels` it returns the ones the point was *annotated*
  on (mapping bipole and unipole, reference), because naming all 78 is not an
  answer. `fetch_waveform` is the undecimated version.
- **`start_ms` / `end_ms` are milliseconds**, converted through the sample
  rate, relative to the start of the stored window, with an exclusive end.
  For annotation-centred analysis, convert the exported annotation offset
  to these window-relative bounds.

## Executable example

The supplied [Python MCP example](https://github.com/swillert/pulse-ep/tree/main/examples/python)
checks a map's bipolar unit, requests the area between 0 and 0.5 mV at a
5 mm distance setting, downloads the acquisition points and computes their
median voltage locally. It executes MCP over stdio without a language model.
An assistant can select the same tools in response to a natural-language request.

## See also

- [CLI reference](../reference/cli.md#pulse-ep-mcp)
- [REST API](../reference/rest-api.md)
- [Managing users](managing-users.md)
