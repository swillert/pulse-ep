# REST API reference

The pulse-ep HTTP API exposes everything the bundled viewer (and every
[cross-language example](../examples/index.md)) consumes. All endpoints
except `/login_user`, the static UI routes (`/`, `/login`, `/register`,
`/dashboard`, `/import`) and standard-user registration require a JWT access token.

Default base URL: `http://127.0.0.1:5000` (configurable via
`PULSE_EP_HOST` / `PULSE_EP_PORT`).

## Authentication

### `POST /login_user`

Exchange username/password for a JWT.

**Request**

```http
POST /login_user
Content-Type: application/json

{ "username": "admin", "password": "…" }
```

**Response**

```json
{ "access_token": "eyJhbGciOiJIUzI1NiI..." }
```

`401 Unauthorized` on bad credentials.

The token carries a `role` claim, and it is enforced: `admin` may do
everything, `user` may read and write, `readonly` is refused on every
endpoint that changes stored state and gets `403` with the role it has and
the roles the endpoint wants. Reads that arrive as `POST` — a filter, an
area integration, a comparison — stay open to `readonly`, because what
decides is what an endpoint does, not the verb it came under.

The token must accompany every subsequent request as
`Authorization: Bearer <token>`. It carries a `role` claim
(`admin` | `user` | `readonly`) and a 15-minute expiry by default
(see Flask-JWT-Extended config in `server/app.py`).

### `POST /register_user`

Create a new user. Registration is open — the bundled UI has a page for it —
but an unauthenticated caller may only ever create a plain `user`. Naming a
privileged role requires an administrator's token; `pulse-ep-create-user`
bootstraps the first one.

```http
POST /register_user
Authorization: Bearer <admin-token>
Content-Type: application/json

{ "username": "clinician_01", "password": "…", "role": "user" }
```

`201 Created` on success; `400` for missing fields or an existing username.

## Studies and maps

### `GET /list_studies`

Returns every study in the database.

```json
[
  { "id": 1, "study_name": "Synthetic CARTO", "vendor": "carto" },
  { "id": 2, "study_name": "Synthetic EnSite", "vendor": "ensite" }
]
```

### `GET /list_epmaps_in_study/<study_id>`

```json
[
  { "id": 12, "study_id": 1, "map_name": "LA-pacemap-001", "number_of_points": 142, "measurement_points": 142 },
  { "id": 13, "study_id": 1, "map_name": "LA-pacemap-002", "number_of_points": 167, "measurement_points": 167 }
]
```

`404` if the study does not exist.

### `POST /get_epmaps`

Bulk metadata fetch for a list of map IDs.

```http
POST /get_epmaps
Authorization: Bearer <token>
Content-Type: application/json

{ "epmap_ids": [12, 13, 14] }
```

```json
[
  { "id": 12, "study_id": 1, "study_name": "AF-2024-01", "map_name": "LA-pacemap-001", "number_of_points": 142 },
  …
]
```

### `GET /get_mesh_data`

The workhorse: per-vertex coordinates, triangle connectivity, scalar field,
and the catheter point cloud for one map.

**Query parameters**

| Param         | Type     | Required | Default | Notes                                                         |
| ------------- | -------- | -------- | ------- | ------------------------------------------------------------- |
| `map_id`      | int      | ✓        |         | Database ID of the EP map.                                    |
| `scalar_name` | string | | map primary | Named field; discover choices at `/epmaps/<id>/scalars`. |
| `distance` | float | | `5.0` | Measurement-distance threshold in display mode, in mm; ignored in raw mode. |
| `representation` | string | | `display` | `display` or `raw`; see the complete analysis export below. |

**Response structure** (schematic; `…` denotes array entries)

```text
{
  "mesh_data": {
    "vertices":                  [[x, y, z], …],
    "faces":                     [[i, j, k], …],
    "scalar_data":               [v, v, null, …],
    "normalized_scalar_data":    [0..1, …]
  },
  "point_data": {
    "coordinates":               [[x, y, z], …],
    "scalar_data":               [v, v, null, …],
    "normalized_scalar_data":    [0..1, …]
  }
}
```

`null` (rendered as `NaN` in numerical clients) marks vertices outside
the `distance` radius and missing point measurements. Indices in
`faces` are zero-based.

## Filtering by attributes

### `POST /epmaps/filter_by_attributes`

Filter maps by the JSONB attributes set by the importer or
`pulse-ep-tag-maps`. The filter is a JSON dict — values are
case-insensitive (`"true"` / `True` are equivalent).

```http
POST /epmaps/filter_by_attributes
Authorization: Bearer <token>
Content-Type: application/json

{ "filters": { "atrium": "LA", "pacemap": true } }
```

```json
{ "map_ids": [12, 13, 14, 15] }
```

If `filters` is empty `{}`, **all** map IDs from `EPMapModel` are returned.

### `POST /epmaps/set_attributes`

Bulk-apply a set of attribute values to a list of map IDs. Admin only.

```http
POST /epmaps/set_attributes
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "map_ids": [12, 13],
  "attribute_values": { "pacemap": true, "operator": "sw" }
}
```

### `POST /epmaps/get_attributes`

Bulk-fetch attribute dicts for a list of map IDs, optionally restricted
to a subset of attribute names.

```http
POST /epmaps/get_attributes
Authorization: Bearer <token>
Content-Type: application/json

{ "map_ids": [12, 13], "attributes": ["pacemap", "atrium"] }
```

```json
{
  "attributes": {
    "12": { "pacemap": true, "atrium": "LA" },
    "13": { "pacemap": true, "atrium": "LA" }
  }
}
```

### `GET /epmaps/distinct_attributes`

The attribute schema — every known attribute name, its data type, and
its default. Driven by `AttributeMetadata`.

```json
{
  "distinct_attributes": [
    { "name": "pacemap", "type": "boolean", "default_value": false },
    { "name": "atrium",  "type": "string",  "default_value": "" }
  ]
}
```

## Per-interval area integration

### `POST /calculate_areas_for_intervals`

The platform's signature reduction: total surface area falling into each
user-supplied score bin.

```http
POST /calculate_areas_for_intervals
Authorization: Bearer <token>
Content-Type: application/json

{
  "map_id": 12,
  "scalar_name": "act",
  "distance": 5.0,
  "intervals": [[50, 60], [60, 70], [70, 80], [80, 90], [90, 100]]
}
```

```json
{ "areas": [0.81, 1.46, 2.84, 3.91, 3.32] }
```

Areas are in cm²; empty bins return `0`. Triangles use the mean of their
finite vertex values; triangles with none are excluded. Adjacent bins are
left-closed and right-open, except the greatest upper endpoint in the request,
which is included. Geometry is unsimplified; hold the distance setting fixed
when comparing results.

## Colormaps

The viewer's editable colorbar lives here.

### `POST /colormaps` (admin)

Create a colormap. See [Colormaps and reports](../guides/colormaps-and-reports.md)
for the field semantics.

```json
{
  "name": "pacemap_clinical",
  "colors":      ["#3a76ff", "#ffd700", "#e34a33"],
  "intervals":   [50, 85, 100],
  "annotations": ["low", "match", "perfect"],
  "use_gradient": false,
  "is_relative":  false,
  "clipping":     true
}
```

### `GET /colormaps`

List all colormaps.

### `GET /colormaps/<name>`

Fetch one colormap by `name`.

### `PUT /colormaps/<id>` (admin)

Update an existing colormap. Same body shape as `POST`.

### `DELETE /colormaps/<id>` (admin)

Remove a colormap.

## Reports

Async clinical Excel generation.

### `POST /save_report`

```json
{
  "report_name": "AF-2024-01 LA pacemaps",
  "colormap_id": 3,
  "colormap_name": "pacemap_clinical",
  "datatype":    "act",
  "distance":    5.0,
  "map_ids":     [12, 13, 14, 15],
  "additional_data": { "indication": "AF redo" }
}
```

Returns `{"message":"Report saved successfully."}` with status 200.
Use `GET /reports` to retrieve the saved report ID.

### `GET /reports`

List all saved reports.

### `DELETE /reports/<report_id>`

Delete the report row. An already generated file is not automatically removed.

### `POST /reports/<report_id>/generate`

Start a background worker that computes the per-map area table and
writes an Excel file to `PULSE_EP_REPORTS_DIR`. Returns `202 Accepted`
immediately.

### `GET /reports/<report_id>/status`

```json
{ "status": "generating", "excel_file": null, "error": null }
```

`status` is one of `generating | ready | error | null` (the last
meaning the report has been saved but `generate` was never called).

### `GET /reports/<report_id>/download`

Stream the generated `.xlsx`. `404` if the report has not been generated
or the file is missing on disk.

## Scalar fields of a map

### `GET /epmaps/<map_id>/scalars`

The quantities this map actually carries. Clients should read the choices
from here rather than assuming any particular field name: the fields
differ per vendor and per map type.

```json
{
  "map_id": 12,
  "primary": "voltage_bipolar",
  "scalars": [
    {"name": "voltage_bipolar", "kind": "voltage_bipolar", "unit": "mV",
     "source": "ensite/6.0.0.683129"},
    {"name": "voltage_unipolar", "kind": "voltage_unipolar", "unit": "mV",
     "source": "ensite/6.0.0.683129"}
  ]
}
```

`primary` names the map's most representative quantity — the one analysis
endpoints use when no `scalar_name` is given. `404` if the map does not
exist.

## Points of a map

### `GET /epmaps/<map_id>/points`

The acquisition points behind a map, with `measurements` flattened to
`{name: value}` and the units stated once for the page.

```json
{
  "map_id": 12, "count": 66, "offset": 0, "returned": 66,
  "units": {"pacemap_score": "%", "voltage_bipolar": "mV"},
  "points": [
    {"point_index": 0, "source_id": "1",
     "position": [-30.996, -14.1332, 104.711],
     "measurements": {"pacemap_score": 96.0, "voltage_bipolar": 196.605},
     "annotations": {"start_time": 13500280, "reference": 2000, "map": 1904,
                     "woi_from": -170, "woi_to": 129},
     "tags": []}
  ]
}
```

`annotations` says where this point's beat sits in the signal recorded for it
— the components its `activation_time` / `pacemap_score` was derived from, and
what tells a client where to look in a downloaded window. A stored waveform
records the same facts under the same names.

`limit` (default 500, `0` = every point) and `offset` page the set. The whole
point set was previously only reachable through
`/get_mesh_data?representation=raw`, which returns the mesh alongside — tens of
thousands of vertices to read a few hundred measurements. `404` if the map
does not exist.

## Signals of a map

### `GET /epmaps/<map_id>/waveforms`

Which signal windows were recorded, without their samples. Listing them was
previously only possible through `/get_mesh_data?representation=raw`, which
drags a whole mesh along to answer "which signals are there".

```json
{
  "map_id": 12,
  "count": 66,
  "waveforms": [
    {"id": 1, "study_id": 3, "map_id": 12, "point_source_id": "1",
     "signal_type": "ecg", "sample_rate": 1000.0,
     "n_samples": 2500, "n_channels": 78,
     "channels": ["M1", "CS1-CS2", "…"],
     "download_url": "/waveforms/1/download"}
  ]
}
```

Rows include the map's own signals and the study-level ones that belong to no
single map. CARTO records one window per acquisition and a multi-electrode
catheter takes several points from it, so **rows can share a `download_url`**:
each row is one point's view of the same stored window. `404` if the map does
not exist.

## Map comparison

### `POST /api/compare`

Delta of one quantity between two maps (`a − b`), projected onto map A's
geometry.

```json
{
  "map_a_id": 12,
  "map_b_id": 13,
  "scalar_name": "voltage_bipolar",
  "metric": "geodesic",
  "max_distance": 10.0
}
```

| Field          | Default     | Notes                                                        |
| -------------- | ----------- | ------------------------------------------------------------ |
| `map_a_id`     |             | Required. The geometry the result lives on.                  |
| `map_b_id`     |             | Required. The map subtracted from A.                         |
| `scalar_name`  |             | Required. Must exist on both maps.                           |
| `metric`       | `euclidean` | `euclidean` (nearest vertex) or `geodesic` (along A's surface). |
| `max_distance` | none        | Correspondences further than this become `NaN`.              |

Geodesic correspondence first projects B vertices to their nearest A vertices,
then propagates along A. Initial projection can still be wrong near folds.
Both metrics require aligned coordinate frames; neither performs registration.
`geodesic_solver` selects `dijkstra` (default) or `heat`; `include_delta=false`
returns statistics without the per-vertex difference array.

## Import queue

All routes below are under `/api/import-jobs` and are JWT-protected.
GET is available to all roles; mutations require `user` or `admin`.
They drive the lifecycle `detected → needs_review → importing → done |
error`; see the [EnSite X import guide](../guides/ensite-import.md#the-import-queue).

| Method + path                        | Purpose                                                     |
| ------------------------------------ | ----------------------------------------------------------- |
| `GET /api/import-jobs`               | List jobs.                                                  |
| `GET /api/import-jobs/<id>`          | One job, including its full plan.                           |
| `POST /api/import-jobs`              | Enqueue an export by path. Auto-detects the vendor.         |
| `POST /api/import-jobs/scan`         | Scan the drop directory for new bundles.                    |
| `POST /api/import-jobs/<id>/prepare` | Build and save the plan; no study data imported.                          |
| `PATCH /api/import-jobs/<id>/plan`   | Store the reviewer's edited plan.                           |
| `POST /api/import-jobs/<id>/commit`  | Execute the plan and persist.                               |

Committing is idempotent by study identity: a study already in the
database is not written again, and the job points at the existing one.

## Error model

pulse-ep uses standard HTTP status codes:

| Status | Meaning                                                |
| ------ | ------------------------------------------------------ |
| 200    | OK.                                                    |
| 201    | Created (after `POST /register_user`, `POST /colormaps`). |
| 202    | Accepted (async report generation kicked off).         |
| 400    | Bad request — validation failure.                      |
| 401    | Missing or invalid JWT.                                |
| 403    | Authenticated but lacks `role` for this endpoint.      |
| 404    | Study / map / colormap / report not found.             |
| 500    | Unexpected server error.                               |

Handled API errors generally use a JSON `msg` or `error`. Framework-level
errors, unknown routes or unhandled exceptions can return HTML; clients should
check the HTTP status and content type before parsing JSON. Invalid or expired
JWTs can also produce status 422 or 401 depending on the failure.

## Rate limits

There are no built-in rate limits. For production deployments, put pulse-ep
behind a reverse proxy and rate-limit there.

## Versioning

Endpoints are unversioned in the current `0.x` series. Consult the
[Changelog](../changelog.md) when upgrading and pin a release for reproducible
workflows. Raw exports additionally identify their payload schema version.

## See also

- [Cross-language examples](../examples/index.md) — same endpoints,
  called from R / MATLAB / ParaView / Jupyter.
- [Data model](data-model.md) — the database schema the API exposes.
- [Configuration](../getting-started/configuration.md) — `PULSE_EP_*`
  variables that affect HTTP behaviour (CORS, JWT, bcrypt rounds).

### Complete analysis export

`GET /get_mesh_data?map_id=ID&representation=raw` (Bearer authentication)
returns schema version `1.0`. The default `representation=display` preserves
the existing repaired, simplified and distance-masked display response.
Raw mode ignores `distance` and does not repair, simplify, project, normalise
or mask the stored data. `scalar_name` selects the convenience `scalar_data`
array; **all** named fields remain available in `mesh_data.scalar_fields`.

Raw means **stored importer-conditioned data**, not a byte-for-byte vendor
archive: decoding and sentinel handling already performed during import
cannot be undone by this endpoint. Coordinates are in mm, triangle areas
in mm², faces are zero-based, and IEEE non-finite values become JSON `null`
without dropping array positions. Normalised arrays are empty in raw mode.

The response includes:

- `mesh_data`: original vertices/faces, all named scalar values with kind,
  unit, status mask and source, normals, edge flags, stored triangle areas
  (possibly absent), and legacy scalar arrays.
- `point_data`: unprojected acquisition coordinates, open per-point
  measurements with units, electrodes, source IDs/order, and legacy CARTO
  rows including annotations and connector geometry.
- `map`, `study`: identifiers, map attributes and stored study provenance.
- `placed_points`: study-level markers with types and attributes.
- `waveforms`: metadata and authenticated `download_url` for each stored
  map waveform and each study-level waveform. Study-level signals are not
  silently assigned to an individual acquisition point.

`GET /waveforms/ID/download` downloads the original stored Parquet file.
It includes channel/timing metadata and requires `PULSE_EP_WAVEFORM_STORE_DIR`
to point to the same store used at import. Missing files return 404; an
unconfigured store returns 503. Signals not imported are not recoverable
through this API. All endpoints use the existing server authentication model.

R: `pe_get_mesh(token, id, representation="raw")`; MATLAB:
`pe_get_mesh(baseURL, token, id, "", 5, "raw")`. Both return the complete
response in `mesh$data` / `mesh.data`, with convenience one-based `faces`
for native computations. The nested response retains zero-based faces.
`pe_download_waveform` writes a Parquet file for Arrow/R or MATLAB parquetread.

ParaView: set **Representation** to `raw`. Output port 0 contains the original
surface and all named fields/validity arrays in double precision; port 1
contains acquisition points with their measured fields. Full metadata,
electrode geometry and signal links remain available as JSON in the
`pulse_ep_export_json` FieldData array on both outputs. `display` remains
the default. Signal samples are downloaded separately rather than replicated
inside every mesh response.

### Interval boundary convention

Adjacent area intervals are left-closed and right-open (`[lo, hi)`), except
that the largest upper endpoint in a request is included. Thus a shared
boundary belongs to its upper bin exactly once. Intentionally overlapping
intervals remain independent queries. Areas use whole-triangle means.
