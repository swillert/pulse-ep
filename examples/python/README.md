# Point-linked CARTO electrograms

`plot_point_waveforms.py` retrieves a raw map, locates an acquisition point
by its **source ID**, follows its waveform reference and downloads the
Parquet object through the authenticated API. It plots the original point's
projection on a PA mesh view and the unipolar, bipolar and reference channels
named in that point's metadata.

## Requirements

- A running pulse-ep service with the map and its CARTO waveforms imported.
  Enable `--waveforms --store-dir PATH` with `pulse-ep-import-carto`, or select
  waveforms in the import plan. Configure the server to read the same store.
- Python with `requests`, `numpy`, `pyarrow`, `matplotlib` and `pyvista`.
- The map ID and acquisition point `source_id`, available in the raw mesh
  response. This is not a mesh vertex index or the database row ID.

Set `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME` and `PULSE_EP_PASSWORD` in your
local environment. Then run, substituting your own IDs:

```sh
python examples/python/plot_point_waveforms.py \
  --map-id 1 --point-id 1000 --output point_waveforms.png
```

The default view shows ±250 ms around the exported reference annotation.
Use `--half-window-ms` to change it. Dashed grey lines mark the reference;
dotted orange lines mark the point's mapping annotation. Amplitudes are
stored millivolt values after the importer applies the export's gain.
The example applies no additional filtering or baseline correction.
Each channel has its own labelled amplitude axis.

The mesh uses the CARTO PA convention (camera on negative Z, positive Y up).
The red marker is the projection of the original acquisition coordinate;
it is not snapped to a mesh vertex or moved onto the surface. The figure
contains clinical anatomy and signals, so review it before sharing.
Neither source data nor credentials are included in this example folder.

## MCP: from a question to an executable analysis

`mcp_analysis.py` executes a fixed tool sequence through a real MCP stdio
session. It represents the tool workflow for this research request:

> For this map, report the surface area with bipolar voltage between 0 and
> 0.5 mV using a 5 mm measurement-distance threshold. Download every acquisition
> point and calculate the median of the finite bipolar point voltages.

Install `pulse-ep[mcp]` and configure `PULSE_EP_MCP_BASE_URL`,
`PULSE_EP_MCP_USERNAME` and `PULSE_EP_MCP_PASSWORD` (or a token).
MCP is disabled by default. Review your institution's rules on data disclosure
before setting `PULSE_EP_MCP_ENABLED=1` on both the service and in the local
MCP process environment. Use a `readonly` account for this example.
Set `PULSE_EP_MCP_DOWNLOAD_DIR` to a private local directory. Run:

```sh
python examples/python/mcp_analysis.py --map-id 1
```

The example starts the MCP server, checks the field and unit through
`map_summary`, calls `area_of_range`, and obtains the complete CSV through
`fetch_points`. Python computes the median from the downloaded file.
Surface area is returned in cm²; the point median is unweighted and in mV.
These describe different data domains: mesh surface versus acquisition points.
The script uses no language model and requires no model-provider credentials.
It is a reproducible protocol example of operations an MCP-connected assistant
can select, not a recorded conversation or a benchmark of model reasoning.
Downloaded point tables can contain sensitive data and remain local.
