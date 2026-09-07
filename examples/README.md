# pulse-ep — example clients

This directory shows how to consume `pulse-ep` from environments other
than the bundled Flask UI. Each subfolder is self-contained — pick the
language you work in.

| Folder        | Language           | What it shows                                                        |
| ------------- | ------------------ | -------------------------------------------------------------------- |
| `paraview/`   | Python (ParaView)  | Load a map directly into ParaView via the REST API, plus a CLI VTU exporter that uses `pulse_ep.core` without a running server. |
| `r/`          | R (httr2 + rgl)    | Minimal REST client, mesh rendering, per-vertex scalar histogram and area-per-interval table returned by the shared service. |
| `matlab/`     | MATLAB (R2020a+)   | `webread` / `webwrite` client, `trisurf` 3D, scalar histogram and area-per-interval table — the same numbers, in MATLAB. |
| `python/` | Python | REST-based point-linked waveform plotting and a separate executable MCP analysis. |
| `notebooks/`  | Jupyter / Python   | End-to-end notebook: login → study browsing → 3D plot with PyVista, scalar histogram and area-per-interval table. |

## Why these examples exist (and what they prove)

These examples connect one shared data service to multiple analysis
environments. They demonstrate both shared server calculations and local
analysis of retrieved arrays. Matching interval-area responses verifies
consistent API use; independent geometric calculations provide a separate
check of the downloaded mesh. The Python waveform example additionally
follows a source point to its stored multichannel recording.

The Python in-memory demo, requiring the installed base package but no database, lives at
[`src/pulse_ep/examples/demo_synthetic.py`](../src/pulse_ep/examples/demo_synthetic.py)
and is wired as the `pulse-ep-demo` console script.

## Common prerequisites

All client examples (everything except `paraview/export_to_vtk.py`) talk
to a running `pulse-ep` server. Start one however you prefer:

```bash
# A. local install
pulse-ep-server                       # http://127.0.0.1:5000

# B. Docker stack
docker compose --profile server up -d --build
```

After configuring and migrating the database, create an account if needed
(use `docker compose exec server` before the command in a Docker deployment):

```bash
pulse-ep-create-user --username admin --role admin
```

The examples expect three environment variables (place them in your
shell `rc` file or pass them inline):

```bash
export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
export PULSE_EP_USERNAME="admin"
export PULSE_EP_PASSWORD="…"
```

A quick smoke test from any shell:

```bash
TOKEN=$(curl -s -X POST "$PULSE_EP_BASE_URL/login_user" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$PULSE_EP_USERNAME\",\"password\":\"$PULSE_EP_PASSWORD\"}" \
    | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
curl -s "$PULSE_EP_BASE_URL/list_studies" -H "Authorization: Bearer $TOKEN"
```

If that prints a JSON array of studies you are ready to run any of the
language-specific examples.

## Environment variables

Two prefixes, on purpose:

| Prefix | What it configures | Read by |
| --- | --- | --- |
| `PULSE_EP_*` | client connection settings (MCP uses `PULSE_EP_MCP_*`) | REST clients |
| `PE_*` | per-run options of these examples only | R, MATLAB |

```bash
# connection
export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
export PULSE_EP_USERNAME="admin"
export PULSE_EP_PASSWORD="…"

# options (optional)
export PE_MAP_ID=12              # which map; default: first map of first study
export PE_SCALAR_NAME=           # empty: the map's own primary quantity
export PE_DISTANCE_MM=5.0        # measurement-distance threshold, mm
export PE_INTERVAL_BREAKS=       # empty: bins derived from the quantity's range
```

`PE_INTERVAL_BREAKS` used to default to the pace-mapping bins 50–100 %, which
meant a bipolar voltage map in mV reported zero area in every bin. The bins now
come from the range the server reports for that quantity.

## REST endpoints used by these examples

These are common endpoints used across the examples; individual scripts use a subset. See `src/pulse_ep/server/app.py`
for the full surface.

| Method | Path                                | Purpose                                                  |
| ------ | ----------------------------------- | -------------------------------------------------------- |
| `POST` | `/login_user`                       | Exchange username/password for a JWT access token.       |
| `GET`  | `/list_studies`                     | List all studies in the database.                        |
| `GET`  | `/list_epmaps_in_study/<study_id>`  | List EP maps in a study.                                 |
| `GET`  | `/get_mesh_data?map_id=&scalar_name=&distance=` | Mesh + per-vertex scalars + measurement points. |
| `POST` | `/calculate_areas_for_intervals`    | Surface area per score bin — the clinical-report reduction. |

## Scope of the reproducibility claim

Histograms are calculated in the client from the returned mesh values.
The interval-area examples call the shared server calculation; they do
not independently reimplement surface integration. The default mesh payload uses the repaired/simplified display representation.
Select `representation=raw` to obtain the original stored geometry and every
field for independent computations. The API documentation describes metadata,
measurement points and authenticated waveform downloads.
