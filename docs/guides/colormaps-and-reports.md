# Colormaps and reports

A colormap defines colour control points at numeric positions. The viewer
uses these to colour a scalar field and submits adjacent positions as
intervals for surface-area calculations.

## Colormap fields

| Field | Meaning |
| --- | --- |
| `name` | Unique saved name |
| `colors` | Hex colour strings, one per control point |
| `intervals` | Numeric positions; **same length as `colors`** |
| `annotations` | Optional labels, same length as `intervals` |
| `use_gradient` | Interpolate between colours or use steps |
| `is_relative` | In the viewer, normalise the field and control-point ranges for colour mapping |
| `clipping` | Use endpoint colours outside the range; otherwise finite out-of-range values are white |

Missing values remain grey. The REST endpoints enforce matching lengths;
there is no equivalent automatic length check on direct ORM construction.

## Default colormaps

```bash
pulse-ep-populate-colormaps
```

The eight presets are `viridis_0_3_mV`, `jet`, `viridis`, `plasma`, `magma`,
`inferno`, `pacemapping_5` and `pacemapping`. Re-running preserves edited
colours and intervals, but synchronises the shipped `is_relative`, `clipping`
and `use_gradient` flags.

## Create or edit

Administrators can use the viewer's colormap form and **Save** button, or the
REST API. A valid three-control-point voltage scale is:

```bash
curl -X POST "$PULSE_EP_BASE_URL/colormaps" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"voltage_example", "colors":["#440154","#21918c","#fde725"],
       "intervals":[0,1.5,3], "annotations":["0","1.5","3"],
       "use_gradient":true, "is_relative":false, "clipping":true}'
```

Here the adjacent analysis intervals are 0–1.5 and 1.5–3 mV. An equivalent
configuration can be constructed with `ColormapModel` using the same lists.

## Fixed bipolar-voltage scale

Select `viridis_0_3_mV` with `voltage_bipolar` for an absolute 0–3 mV scale.
It uses the same nine Viridis control points as the publication's ParaView
view, rounded to 8-bit sRGB. Relative normalisation is disabled and endpoint
clipping enabled. The mesh converts these sRGB colours to Three.js linear
vertex colours before rendering. Display geometry and lighting can still
affect the appearance compared with another application.

## Excel reports

A report saves map IDs, colormap, scalar and measurement-distance settings.
Install the `figures` extra for Excel generation.

1. `POST /save_report` stores the configuration and returns a success message.
2. `GET /reports` lists saved reports and their IDs.
3. `POST /reports/<id>/generate` starts background generation.
4. `GET /reports/<id>/status` reports `generating`, `ready`, `error` or `null`.
5. `GET /reports/<id>/download` downloads the generated XLSX.

The table contains map identifiers, total area, scalar statistics, interval
areas and map attributes. For each numeric interval it reports an absolute
area and a separate relative area obtained by interpreting the bounds as
percentages of that map's maximum. This report convention is distinct from
the viewer's min–max colour normalisation. Use absolute voltage intervals for
physical voltage thresholds; do not interpret a relative column as a clinical
voltage threshold without specifying its reference.

Generated files are written to `PULSE_EP_REPORTS_DIR`. Deleting a report removes
its database row; it does not automatically remove an already generated file.

## Live calculations

`POST /calculate_areas_for_intervals` calculates areas synchronously. The
viewer, R, MATLAB and Jupyter examples call this same operation. Histograms
and independent geometric calculations can instead use downloaded raw arrays.
Adjacent bins are half-open except for the greatest upper endpoint, which is
included. Empty bins return zero.

See the [REST API reference](../reference/rest-api.md) for request and response shapes.
