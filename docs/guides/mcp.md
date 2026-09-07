# The MCP server

`pulse-ep-mcp` exposes a deployment to an AI client (Claude Desktop, Claude
Code, any MCP host) over the [Model Context
Protocol](https://modelcontextprotocol.io) — read-only, and with study
identity anonymised by default.

## What it is for

If you already have a SQL tool pointed at the pulse-ep database, you can
already ask "which studies are there". This server exists for the three things
SQL on that database cannot answer:

- **Signal samples are not in the database.** They live beside it as Parquet;
  the table holds a `data_uri` and nothing else. `read_waveform` returns the
  trace of a named channel around a point's annotation.
- **`scalar_fields` is a JSONB blob of tens of thousands of numbers per
  field.** Selecting it is unreadable and blows any context window;
  `map_summary` answers what a map measured, in what unit, over what range.
- **Area, comparison and geodesic correspondence are computation, not
  query.** `area_of_range` and `compare_maps` run them and return the result.

It is a client of the same JWT REST API as the viewer and the `examples/`
clients — there is no privileged path into the database — so it sees exactly
what the account it logs in with can see.

## Switching it off

`PULSE_EP_MCP_ENABLED=0`. One setting, read at both ends, so a shared
environment turns off both with one line:

- **On the server** it is the one that decides for the deployment. Requests
  that identify themselves as MCP are refused with `403`; the viewer, the
  example clients and every other consumer are untouched.
- **On the MCP server** it refuses to start: it prints why on stderr and exits
  0 — switched off on purpose is not a crash, and a client that restarts a
  "failed" server would otherwise fight the setting. `--disabled` does the
  same for one run, `--enabled` overrides the environment.

```console
$ pulse-ep-mcp --check                 # deployment has it off
pulse-ep-mcp: http://pulse-ep.local does not serve MCP access
              (PULSE_EP_MCP_ENABLED=0 on the server)
$ echo $?
3
```

!!! warning "A gate, not a boundary"

    The MCP names itself in a request header, honestly. Anything it can do, a
    person holding the same credentials can do with `curl` — so the server
    switch stops a **forgotten, inherited or misconfigured** MCP, which is the
    case that actually happens. It does not stop someone who wants in.

    What does: the account. Give the MCP its own read-only user, and disable
    that user when access should end. The header is also worth having on its
    own — AI access is visible in the server log as
    `X-Pulse-EP-Client: pulse-ep-mcp/<version>`, distinguishable from a person
    at the viewer.

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
| Map names, quantities, units, values, signals | **untouched** — anatomy and measurements, not identifiers |
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
pip install "pulse-ep[mcp]"
```

The server talks to a running `pulse-ep-server`, so configure where that is
and how to log in:

| Variable | Meaning |
| -------- | ------- |
| `PULSE_EP_MCP_BASE_URL` | pulse-ep server (default `http://localhost:5000`) |
| `PULSE_EP_MCP_TOKEN` | a JWT, if you have one … |
| `PULSE_EP_MCP_USERNAME` / `PULSE_EP_MCP_PASSWORD` | … or an account to log in with |
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
        "PULSE_EP_MCP_BASE_URL": "http://127.0.0.1:5000",
        "PULSE_EP_MCP_USERNAME": "readonly",
        "PULSE_EP_MCP_PASSWORD": "…"
      }
    }
  }
}
```

For Claude Code: `claude mcp add pulse-ep -- /path/to/.venv/bin/pulse-ep-mcp`.

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

The `fetch_*` tools hand over the complete stored data. They write it into the
download directory and return the **path**, rather than putting it in the
answer, and the reason is a measurement rather than a principle. One real
map — 10 129 vertices, five scalar fields, 66 points, 66 signal windows:

| | |
| --- | --- |
| `fetch_map` as a file | 3.2 MB JSON, answer is ~10 lines |
| the same payload `inline=True` | 3 248 423 characters into the context |
| `fetch_points` | 3.7 kB CSV, 66 rows × 9 columns |
| `fetch_waveform` | 293 kB Parquet, 2500 × 78 |

A model that has the data in a file can compute with it — load the CSV in
pandas, open the Parquet, feed the mesh to a script. A model that has it
pasted into its context has spent the room it needed to think.

Where the data is genuinely small, it comes inline: `read_points(map_id,
limit=0)` returns all 66 points of that map in 13 kB, and
`read_waveform(..., max_samples=2500)` returns an undecimated window (51 kB
for three channels). Use `inline=True` on `fetch_map` when you really want the
whole thing in the answer; the response tells you how big it was.

Downloads land in `PULSE_EP_MCP_DOWNLOAD_DIR` (default: a `pulse-ep-mcp`
folder in the system temp directory), and only there — a `filename` argument
is reduced to its basename, so nothing can be written outside it. Written
files are anonymised the same way the answers are: the model can read them,
so they have to hold the same line.

### The remaining limits

- **`compare_maps` never fetches the per-vertex delta** — statistics only.
  Fetch both maps if you want to compute your own.
- **`read_waveform` decimates the trace, but computes statistics over every
  sample**, so a peak that falls between two returned samples is still
  reported. Without `channels` it returns the ones the point was *annotated*
  on (mapping bipole and unipole, reference), because naming all 78 is not an
  answer. `fetch_waveform` is the undecimated version.
- **`start_ms` / `end_ms` are milliseconds**, converted through the sample
  rate — 500 ms is 500 samples on CARTO at 1 kHz and 1000 on a 2 kHz EnSiteX
  segment.

## A typical session

> Which quantities does map 1 carry, and how much of it is a good pace match?

```
map_summary(1)      -> pacemap_score 57.6 … 93.4 %, contact_force, voltage_bipolar, …
area_of_range(1, 90, 100, scalar_name="pacemap_score")
                    -> area 7.7
read_waveform(1)    -> M1 / MCC_Abl_BiPolar_1 / CS1-CS2 around the annotation
```

> Now correlate the pace-match score with contact force across the points.

```
fetch_points(1)     -> /tmp/pulse-ep-mcp/map-1-points.csv, 66 rows
                       (then load it in pandas and compute)
```

## See also

- [CLI reference: `pulse-ep-mcp`](../reference/cli.md#pulse-ep-mcp)
- [REST API](../reference/rest-api.md) — the endpoints the server is a client of
