# pulse-ep + ParaView

Two complementary ways to inspect a CARTO map in ParaView:

1. **Live, via REST** — run [`paraview_pulse_ep.py`](paraview_pulse_ep.py)
   as a *Programmable Source* inside ParaView. No file export, the map
   is fetched from a running `pulse-ep` server every time you press
   *Apply*. Best for browsing many maps interactively.
2. **One-off file export** — use [`export_to_vtk.py`](export_to_vtk.py)
   to dump a single map to a `.vtu` file using `pulse_ep.core` directly
   (no server required, just DB access). Best for sharing maps with
   collaborators or archiving.

Tested against ParaView 5.11 and 5.12 on Linux and macOS.

## 1. Programmable Source (live REST)

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
(`SCALAR_NAME`) plus an additional `point_normalized` array. Pick
*Coloring → SCALAR_NAME* in the *Properties* panel to see the field.

## 2. CLI file export

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

## Notes

- The `distance` parameter to `/get_mesh_data` controls how far around
  measurement points the per-vertex interpolation happens; ParaView
  receives `NaN` outside that radius (which ParaView colors as the
  background). Default is `5.0` mm.
- For Heat-Method geodesics and σ-decay analysis use the
  [`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay)
  package; these examples deliberately stop at "load and display".
