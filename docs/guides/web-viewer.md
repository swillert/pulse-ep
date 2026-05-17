# The web viewer

`pulse-ep` ships a browser-based 3D viewer built on Three.js / WebGL. It
is the *fastest* way for a clinician or co-author to look at an imported
study — no Python install, no API key, just a URL.

## What the viewer does

The viewer is a thin JavaScript client that talks to the same JWT-protected
REST API as every other client. On the home screen it shows the list of
studies; clicking a study reveals its EP maps; clicking a map opens the
interactive 3D inspector.

The inspector renders the triangulated chamber mesh, colored by the
selected scalar field (activation time, bipolar voltage, pace-mapping
similarity, …). It supports:

- orbit / pan / zoom with the mouse,
- per-vertex value readout on hover,
- a colorbar with editable intervals (the changes round-trip through the
  `colormaps` REST endpoint),
- toggling the catheter point cloud overlay,
- saving the current view as a "report" that can later be downloaded as
  an Excel sheet of per-interval areas.

## Logging in

The viewer is reachable at the host/port configured by
`PULSE_EP_HOST` / `PULSE_EP_PORT` (default `http://127.0.0.1:5000`).

You will land on the login screen and need a username and password. Bootstrap
the first admin user via [`pulse-ep-create-user`](../reference/cli.md#pulse-ep-create-user):

```bash
pulse-ep-create-user --username admin --role admin
```

See [Managing users](managing-users.md) for the full role model.

## A typical session

1. **Login** with the admin credentials. The dashboard lists studies
   most recently imported.
2. **Pick a study**. The map list shows each EP map with its name,
   number of points, and any attributes set via the importer or
   [`pulse-ep-tag-maps`](../reference/cli.md#pulse-ep-tag-maps).
3. **Open a map**. The inspector loads in a couple of seconds — about
   500 ms of REST latency for a typical 5 000-vertex atrial mesh, plus
   the WebGL setup.
4. **Choose a scalar**. The drop-down lists `act` (local activation
   time), `voltage`, and any pace-mapping channels present.
5. **Adjust the colormap**. Click the colorbar to drag interval
   boundaries; the changes save to the database immediately.
6. **Save a report**. The viewer's "Save report" action stores the
   current map + colormap + interval configuration as a `ReportModel`.
   The report can then be downloaded as a clinical-format Excel file
   (one row per map, columns for total area and per-interval area).

## Filtering many maps at once

For studies with dozens of pace-maps, the dashboard exposes an
attribute filter. Anything that lives in `EPMapAttributes` —
including the `pacemap`, `atrium`, and any custom tags from the
import CSV — becomes a filter dimension. Typical workflow:

1. Filter by `atrium = LA, pacemap = true` to get the left-atrial
   pace-maps of the current study.
2. Multi-select the filtered maps.
3. Either open them side-by-side, or save them as a single report
   to generate one consolidated Excel sheet.

## Architecture (one paragraph)

The viewer is served as static files from `pulse_ep.server.app` and uses
the REST endpoints documented in the
[REST API reference](../reference/rest-api.md). The mesh comes from
`GET /get_mesh_data` as JSON; the per-interval areas come from
`POST /calculate_areas_for_intervals`; reports go through
`POST /save_report`, `POST /reports/<id>/generate`,
`GET /reports/<id>/status`, `GET /reports/<id>/download`. Nothing the
viewer does is privileged — see the [examples](../examples/index.md)
for the same operations in R, MATLAB, and Python.

## Performance notes

- Mesh JSON payloads are roughly 200 KB to 2 MB per map. The
  `distance` query parameter (interpolation radius) controls how many
  vertices receive a scalar value; smaller radii produce smaller
  responses.
- The Three.js side is happy with up to ~50 000 vertices per mesh on a
  laptop GPU. Larger meshes work but get sluggish.
- Excel report generation runs in a background thread on the server
  (see `POST /reports/<id>/generate`). Polling
  `GET /reports/<id>/status` is the right pattern for the client.

## Troubleshooting

??? failure "Blank canvas, browser console shows `WebGL not available`"

    The viewer requires WebGL 2.0. Update your browser; on locked-down
    workstations check that hardware acceleration is enabled in your
    browser settings.

??? failure "Login succeeds but no studies appear"

    Either the database is empty (run
    [`pulse-ep-import-carto`](../reference/cli.md#pulse-ep-import-carto)) or your user
    lacks read permissions on the `studies` table. The default `admin`
    role has full access; a `user` role is read-only.

??? failure "Scalar field shows up as a uniform grey blob"

    The vertices are too far from any catheter point for the
    `distance`-radius interpolation to produce a value. Increase the
    radius from the inspector toolbar, or pass a larger `distance`
    parameter when querying the REST API.

## See also

- [REST API reference](../reference/rest-api.md) — what the viewer
  actually calls.
- [Managing users](managing-users.md) — role and permission model.
- [Colormaps and reports](colormaps-and-reports.md) — the data model
  behind the inspector's colorbar.
