# Examples

Cross-language client code for ParaView, R, MATLAB and Jupyter. The
canonical source lives in the
[`examples/`](https://github.com/swillert/pulse-ep/tree/main/examples)
directory of the repository; this page is the documentation index.

## Why these examples exist

These examples connect the same stored maps to established analysis tools.
Histograms are computed locally from downloaded values, while the interval-area
examples request the shared server operation. Full raw arrays also support
independent calculations; the publication supplement executes and records
separate geometry checks in R and MATLAB.

## Catalogue

<div class="grid cards" markdown>

-   :material-cube-scan:{ .lg .middle } __ParaView__

    ---

    Load either vendor through the native source plugin or Programmable
    Source. Raw mode exposes the surface, every field and a separate point
    output. A VTU exporter uses direct database access.

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

## Python and MCP examples

[`examples/python`](https://github.com/swillert/pulse-ep/tree/main/examples/python)
contains a REST waveform plot and a separate MCP stdio analysis. Follow the
[MCP guide](../guides/mcp.md) for explicit opt-in and client configuration.

## Common prerequisites

The REST clients require a running, configured service with imported studies
and a user account. See the [Quickstart](../getting-started/quickstart.md).
A `readonly` account is sufficient for retrieval and calculations. The VTU
exporter uses direct PostgreSQL access instead.

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

Common endpoints used across these examples:

| Method | Path                                            | Purpose |
| ------ | ----------------------------------------------- | ------- |
| `POST` | `/login_user`                                   | JWT issuance. |
| `GET`  | `/list_studies`                                 | Study catalogue. |
| `GET`  | `/list_epmaps_in_study/<study_id>`              | Map catalogue. |
| `GET`  | `/get_mesh_data?map_id=&scalar_name=&distance=` | Mesh + scalars + points. |
| `POST` | `/calculate_areas_for_intervals`                | Per-interval surface area. |

Full request/response shapes: [REST API reference](../reference/rest-api.md).
