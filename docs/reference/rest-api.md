# REST API reference

The pulse-ep HTTP API exposes everything the bundled viewer (and every
[cross-language example](../examples/index.md)) consumes. All endpoints
except `/login_user`, the static UI routes (`/`, `/login`, `/register`,
`/dashboard`) and `/register_user` require a JWT access token.

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

The token must accompany every subsequent request as
`Authorization: Bearer <token>`. It carries a `role` claim
(`admin` | `user`) and a 1-hour expiry by default
(see Flask-JWT-Extended config in `server/app.py`).

### `POST /register_user`

Create a new user. **Admin only** in the current release.

```http
POST /register_user
Authorization: Bearer <admin-token>
Content-Type: application/json

{ "username": "clinician_01", "password": "…", "role": "user" }
```

`201 Created` on success; `400` if username already exists.

## Studies and maps

### `GET /list_studies`

Returns every study in the database.

```json
[
  { "id": 1, "study_name": "AF-2024-01" },
  { "id": 2, "study_name": "AFL-2024-03" }
]
```

### `GET /list_epmaps_in_study/<study_id>`

```json
[
  { "id": 12, "study_id": 1, "map_name": "LA-pacemap-001", "number_of_points": 142 },
  { "id": 13, "study_id": 1, "map_name": "LA-pacemap-002", "number_of_points": 167 }
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
| `scalar_name` | string   |          | `act`   | Per-vertex scalar (`act` / `voltage` / `similarity_score` / …). |
| `distance`    | float    |          | `5.0`   | Interpolation radius in mm. Vertices farther than `distance` from any catheter point receive `NaN`. |

**Response**

```json
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

Areas are in cm². `null` marks empty bins. Bins are interpreted as
half-open `[lo, hi)`.

## Colormaps

The viewer's editable colorbar lives here.

### `POST /colormaps` (admin)

Create a colormap. See [Colormaps and reports](../guides/colormaps-and-reports.md)
for the field semantics.

```json
{
  "name": "pacemap_clinical",
  "colors":      ["#3a76ff", "#ffd700", "#e34a33"],
  "intervals":   [50, 70, 85, 100],
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

Returns the new `report_id`.

### `GET /reports`

List all saved reports.

### `DELETE /reports/<report_id>`

Delete a report (the row + the generated file, if any).

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

Error responses always have a JSON body with at least `msg` or `error`
keys; clients should not need to parse free-form HTML.

## Rate limits

There are no built-in rate limits. For production deployments, put pulse-ep
behind a reverse proxy and rate-limit there.

## Versioning

Endpoints are unversioned in `0.1.x` — the API surface is still firming
up. From `1.0.0` onwards (cut when the SoftwareX paper is accepted),
breaking changes will be reflected in a major-version bump and an
explicit deprecation notice in the [Changelog](../changelog.md).

## See also

- [Cross-language examples](../examples/index.md) — same endpoints,
  called from R / MATLAB / ParaView / Jupyter.
- [Data model](data-model.md) — the database schema the API exposes.
- [Configuration](../getting-started/configuration.md) — `PULSE_EP_*`
  variables that affect HTTP behaviour (CORS, JWT, bcrypt rounds).
