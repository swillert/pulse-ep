# Examples

Cross-language client code for ParaView, R, MATLAB and Jupyter. The
canonical source lives in the
[`examples/`](https://github.com/swillert/pulse-ep/tree/main/examples)
directory of the repository; this page is the documentation index.

## Why these examples exist

These examples form the **cross-language reproducibility statement of
the software paper**: from one CARTO study, served by one REST endpoint,
four independent toolchains compute identical platform-level reductions
— the per-vertex scalar histogram and the per-interval surface-area
breakdown (`/calculate_areas_for_intervals`). If a clinical co-author
in MATLAB and a stats co-author in R get the same numbers as the
Python toolkit and the bundled web viewer, the platform itself is
faithful — independent of any one stack.

## Catalogue

<div class="grid cards" markdown>

-   :material-cube-scan:{ .lg .middle } __ParaView__

    ---

    Load a CARTO map directly into ParaView via the REST API
    (Programmable Source), or use the CLI exporter to write a `.vtu`
    file without a running server.

    [:octicons-arrow-right-24: View on GitHub](https://github.com/swillert/pulse-ep/tree/main/examples/paraview)

-   :simple-r:{ .lg .middle } __R__

    ---

    `httr2`-based REST client and demo: render the mesh with `rgl`,
    plot the scalar histogram with `ggplot2`, tabulate per-interval
    areas.

    [:octicons-arrow-right-24: View on GitHub](https://github.com/swillert/pulse-ep/tree/main/examples/r)

-   :material-language-matlab:{ .lg .middle } __MATLAB__

    ---

    `webread` / `webwrite` client and demo (R2020a+). `trisurf` 3D,
    histogram and area-per-interval table — same numbers, different
    language.

    [:octicons-arrow-right-24: View on GitHub](https://github.com/swillert/pulse-ep/tree/main/examples/matlab)

-   :simple-jupyter:{ .lg .middle } __Jupyter__

    ---

    End-to-end notebook: login → study browsing → 3D plot with
    PyVista → scalar histogram → area-per-interval table as a
    `pandas` DataFrame.

    [:octicons-arrow-right-24: View on GitHub](https://github.com/swillert/pulse-ep/tree/main/examples/notebooks)

</div>

## Common prerequisites

All client examples (everything except `paraview/export_to_vtk.py`) talk
to a running pulse-ep server.

```bash
# A. local install
pulse-ep-server                       # http://127.0.0.1:5000

# B. Docker stack
docker compose --profile server up -d --build

# Bootstrap an admin user once
pulse-ep-create-user --username admin --role admin
```

Then export three environment variables in the shell that runs the
examples:

```bash
export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
export PULSE_EP_USERNAME="admin"
export PULSE_EP_PASSWORD="…"
```

A quick JWT smoke test:

```bash
TOKEN=$(curl -s -X POST "$PULSE_EP_BASE_URL/login_user" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$PULSE_EP_USERNAME\",\"password\":\"$PULSE_EP_PASSWORD\"}" \
    | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
curl -s "$PULSE_EP_BASE_URL/list_studies" -H "Authorization: Bearer $TOKEN"
```

## Endpoints exercised by the examples

The four endpoints every example touches:

| Method | Path                                            | Purpose |
| ------ | ----------------------------------------------- | ------- |
| `POST` | `/login_user`                                   | JWT issuance. |
| `GET`  | `/list_studies`                                 | Study catalogue. |
| `GET`  | `/list_epmaps_in_study/<study_id>`              | Map catalogue. |
| `GET`  | `/get_mesh_data?map_id=&scalar_name=&distance=` | Mesh + scalars + points. |
| `POST` | `/calculate_areas_for_intervals`                | Per-interval surface area. |

Full request/response shapes: [REST API reference](../reference/rest-api.md).
