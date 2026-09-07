# pulse-ep + ParaView

Three ways in, in the order you probably want them:

1. **The plugin** — [`pulse_ep_plugin.py`](pulse_ep_plugin.py). Load it once
   and pulse-ep is in the *Sources* menu, with map, quantity and distance as
   ordinary property widgets. Live over REST, and the selection is saved in
   the ParaView state file. This is the intended integration.
2. **Programmable Source** — [`paraview_pulse_ep.py`](paraview_pulse_ep.py),
   pasted into a script box. Same data path, nothing to install; useful when
   you cannot or would rather not load a plugin.
3. **File export** — [`export_to_vtk.py`](export_to_vtk.py) writes a `.vtu`
   through `pulse_ep.core` (database access, no server). A snapshot: right
   for archiving or for sending a map to someone with no server access,
   wrong for browsing, since every change means exporting again.

The publication verification uses ParaView 6.1.1 on macOS.

## 1. The plugin

```bash
export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
export PULSE_EP_USERNAME="admin"
export PULSE_EP_PASSWORD="…"
paraview &                       # launch from this shell, so it inherits them
```

*Tools → Manage Plugins → Load New…*, pick `pulse_ep_plugin.py`, and tick
**Auto Load** so it comes back next time. Then **Sources → pulse-ep Map**,
set *MapID*, press **Apply**.

| Property | Meaning |
| --- | --- |
| `ServerURL` | empty: `$PULSE_EP_BASE_URL` |
| `Username` | empty: `$PULSE_EP_USERNAME` |
| `MapID` | see `GET /list_epmaps_in_study/<study_id>` |
| `ScalarName` | empty: the map's **primary** quantity, resolved by the server — depending on the fields present, for example `activation_time` or `voltage_bipolar` |
| `Distance` | Measurement-distance threshold in display mode, mm |
| `Representation` | `display` (default) or `raw`; raw preserves all stored geometry and fields |

The **password is never a property**: it is read from `$PULSE_EP_PASSWORD`
only. ParaView writes property values into state files and Python traces, and
a password does not belong in either.

Missing scalar entries arrive as NaN and use the selected colour transfer
function's NaN colour.

From `pvpython`, the proxy is `PulseEPMapSource` and the convenience function
is `pulseepMap` — ParaView derives that name from the menu label:

```python
import paraview.simple as pvs
pvs.LoadPlugin("examples/paraview/pulse_ep_plugin.py", remote=False, ns=globals())
src = pvs.pulseepMap(registrationName="LA map")
src.MapID = 12
src.UpdatePipeline()
```

## 2. Programmable Source (live REST)

1. Start a `pulse-ep` server and make sure your shell has
   `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME`, `PULSE_EP_PASSWORD` set
   (see [`../README.md`](../README.md)).
2. Launch ParaView from the **same shell** so it inherits the env vars.
3. **Sources → Programmable Source**.
4. **Output DataSet Type:** `vtkPolyData`.
5. **Script:** paste the entire contents of
   [`paraview_pulse_ep.py`](paraview_pulse_ep.py).
6. In the script, set `MAP_ID` and (optionally) `SCALAR_NAME` and
   `DISTANCE` near the top, then press **Apply**.

The result is a `vtkPolyData` with one point-data array
(the resolved scalar name) plus an additional `point_normalized` array. Pick
*Coloring → SCALAR_NAME* in the *Properties* panel to see the field.

## 3. CLI file export

```bash
# from the repo root, with `pulse-ep[all]` installed
python examples/paraview/export_to_vtk.py \
    --map-id 25 \
    --scalar-name act \
    --output /tmp/map_25.vtu

# then in ParaView: File → Open → /tmp/map_25.vtu
```

This path talks directly to PostgreSQL through `pulse_ep.core` — no
running HTTP server needed.

## Note

In display mode, `distance` controls masking around measurement positions;
it does not select a new interpolation algorithm. Raw mode ignores it.
The default is 5 mm.

## Which quantity is plotted

Leave `SCALAR_NAME` (or `--scalar-name`) unset and the map's own **primary
quantity** is used — a CARTO map is usually about `activation_time`, an
EnSite X one about `voltage_bipolar`. The exporter prints the name it chose,
and `/get_mesh_data` echoes it as `scalar_name`.

To see what a map offers:

```bash
curl -s "$PULSE_EP_BASE_URL/epmaps/<id>/scalars" -H "Authorization: Bearer $TOKEN"
```

The old default was `act`, a CARTO-only name that no EnSite X map answers to.
It still resolves for CARTO studies, but no longer works as a default.

## Full analysis data

The API now supports `representation=raw`, including every stored field,
measurement, electrode position, marker, provenance and waveform download links.
R and MATLAB retain the complete response in `data`; ParaView exposes raw
surface fields and a second acquisition-point output. See the
[API contract](../../docs/reference/rest-api.md#complete-analysis-export) for
units, missing values and the distinction between stored and vendor-original data.
