# Colormaps and reports

The viewer's colorbar and the Excel reports are two surfaces of the
same underlying concept: a **colormap** — a list of color steps with
matching score intervals — defines how scalar fields are visualised in
3D **and** how the per-interval area breakdown is computed.

## The colormap model

A `ColormapModel` row has:

| Field         | Notes                                                                 |
| ------------- | --------------------------------------------------------------------- |
| `name`        | Unique. Human-readable identifier (e.g. `pacemap_default`).           |
| `colors`      | List of CSS hex strings, one per interval (`["#3a76ff", "#ffd700", "#e34a33"]`). |
| `intervals`   | List of score boundaries; length = `len(colors) + 1`.                 |
| `annotations` | Optional labels per interval (e.g. `["below threshold", "match", "perfect"]`). |
| `use_gradient`| If `true`, smoothly interpolate between colors; if `false`, hard steps. |
| `is_relative` | If `true`, intervals are interpreted as percentages of the per-map max score. |
| `clipping`    | If `true`, values outside `intervals[0]..intervals[-1]` are clipped to the nearest interval. If `false`, they get `NaN` and render as grey. |

The constraint `len(intervals) == len(colors) + 1` is enforced by the
REST endpoint and at the ORM level.

## Bootstrapping the default colormaps

```bash
pulse-ep-populate-colormaps
```

This loads three named colormaps appropriate for pace-mapping similarity
scores (50–100 %, 5-step rainbow), activation time, and bipolar voltage.
Run it once after the first import; re-running is safe (idempotent
upsert by `name`).

## Creating and editing colormaps

### From the viewer

The inspector's colorbar is editable: drag interval boundaries to
re-bin, double-click a color stop to change it. Changes are saved to
the database immediately via `PUT /colormaps/<id>`.

### From the REST API

```bash
curl -X POST "$PULSE_EP_BASE_URL/colormaps" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "pacemap_clinical",
        "colors":     ["#1a3a8c", "#3a76ff", "#ffd700", "#ff8c1a", "#e34a33"],
        "intervals":  [50, 70, 80, 90, 95, 100],
        "annotations":["below-50", "70-80", "80-90", "90-95", "95-100"],
        "use_gradient": false,
        "is_relative": false,
        "clipping": true
    }'
```

### From Python

```python
from pulse_ep import get_db_session, ColormapModel

with get_db_session() as s:
    cm = ColormapModel(
        name="pacemap_clinical",
        colors=["#1a3a8c", "#3a76ff", "#ffd700", "#ff8c1a", "#e34a33"],
        intervals=[50, 70, 80, 90, 95, 100],
        annotations=["below-50", "70-80", "80-90", "90-95", "95-100"],
        use_gradient=False,
        is_relative=False,
        clipping=True,
    )
    cm.create(s)
```

## Reports

A **report** is a saved configuration: a list of map IDs, a colormap,
a scalar name (`act`, `voltage`, …) and an interpolation radius. It
serializes a per-map breakdown of surface area into each colormap bin,
ready for an Excel sheet that fits the clinical reporting template.

### Workflow

1. **Save a report** — `POST /save_report` records the configuration.
2. **Generate the Excel** — `POST /reports/<id>/generate` starts a
   background worker that computes the per-map area table and writes
   it to disk in `PULSE_EP_REPORTS_DIR`.
3. **Poll for status** — `GET /reports/<id>/status` returns
   `generating | ready | error`.
4. **Download** — `GET /reports/<id>/download` streams the `.xlsx` file.

The viewer drives all four steps; CLI / scripted clients call the same
endpoints directly.

### What ends up in the Excel

One sheet, one row per map. Columns:

| Column                       | Meaning                                            |
| ---------------------------- | -------------------------------------------------- |
| `ID`, `Study`, `Map Name`    | Identifiers.                                       |
| `Total Area (cm²)`           | Total mesh surface area.                           |
| `Min` / `Max` / `Mean` / `Std` | Scalar-field summary statistics.                  |
| `<lo>–<hi> (abs)`            | Surface area falling in this absolute score bin.   |
| `<lo>–<hi> (rel)`            | Same bin, but bounds rescaled to the per-map max.  |
| any `EPMapAttributes` key    | Pacemap flag, atrium, operator, …                  |

The headers are styled with a `header_fill` (CARTO-style navy) and
column widths are auto-fitted. The file lives in
`PULSE_EP_REPORTS_DIR` and is served via `send_file` with the
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
MIME type.

## When to compute areas live vs. saved reports

| Endpoint                                        | When to use it                                          |
| ----------------------------------------------- | ------------------------------------------------------- |
| `POST /calculate_areas_for_intervals`           | Interactive single-map probing in the viewer or an R / MATLAB / Jupyter client. Synchronous, fast (<200 ms typical). |
| `POST /save_report` + `/generate` + `/download` | Batch over many maps, snapshot for clinical archive. Asynchronous, persistent file output. |

The [cross-language examples](../examples/index.md) demonstrate the
synchronous endpoint in R, MATLAB and Jupyter — the same numbers the
saved Excel reports contain, computed independently in each toolchain.

## See also

- [REST API → Colormaps](../reference/rest-api.md#colormaps)
- [REST API → Reports](../reference/rest-api.md#reports)
- [Data model: `ColormapModel`, `ReportModel`](../reference/data-model.md)

## Fixed bipolar-voltage scale

`pulse-ep-populate-colormaps` also supplies `viridis_0_3_mV`. Select it
with `voltage_bipolar` in the web viewer for an absolute 0–3 mV scale.
It uses the same nine Viridis control points as the publication's ParaView
view, rounded to 8-bit sRGB. Values below zero use the first colour; values
above 3 mV use the last colour. Missing values remain grey. Relative
normalisation is disabled and endpoint clipping is enabled.

The mesh converts sRGB colormap values to Three.js linear vertex colours
before rendering, so its colours agree with the legend. Geometry processing,
missing values and lighting in other applications may still change how
individual surface regions appear.
