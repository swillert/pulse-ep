# pulse-ep — example clients

This directory shows how to consume `pulse-ep` from environments other
than the bundled Flask UI. Each subfolder is self-contained — pick the
language you work in.

| Folder        | Language           | What it shows                                                        |
| ------------- | ------------------ | -------------------------------------------------------------------- |
| `paraview/`   | Python (ParaView)  | Load a CARTO map directly into ParaView via the REST API, plus a CLI VTU exporter that uses `pulse_ep.core` without a running server. |
| `r/`          | R (httr2 + rgl)    | Minimal REST client and a demo that renders the mesh and plots the per-vertex scalar distribution. |
| `matlab/`     | MATLAB (R2020a+)   | `webread` / `webwrite` client and a `trisurf` 3D visualisation.      |
| `notebooks/`  | Jupyter / Python   | End-to-end notebook: login → study browsing → 3D plot with PyVista. |

> The σ-resolution analysis (Heat-Method geodesics + Gaussian decay fit)
> is a separate scientific contribution and lives in
> [`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay).
> These pulse-ep examples deliberately stop at data access and basic
> visualisation.

The Python end-to-end demo without any external dependencies lives at
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

Create an admin user if you have not already:

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

## REST endpoints used by these examples

These are the four endpoints every example touches. See `src/pulse_ep/server/app.py`
for the full surface.

| Method | Path                                | Purpose                                                  |
| ------ | ----------------------------------- | -------------------------------------------------------- |
| `POST` | `/login_user`                       | Exchange username/password for a JWT access token.       |
| `GET`  | `/list_studies`                     | List all studies in the database.                        |
| `GET`  | `/list_epmaps_in_study/<study_id>`  | List EP maps in a study.                                 |
| `GET`  | `/get_mesh_data?map_id=&scalar_name=&distance=` | Mesh + per-vertex scalars + measurement points. |

All scientific analysis (Heat-Method geodesics, σ-decay fits, focality)
is in the companion package
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay) and
intentionally not duplicated in these client examples.
