# pulse-ep + MATLAB

Files in this directory:

- Separate client functions: [`pe_login.m`](pe_login.m),
  [`pe_list_studies.m`](pe_list_studies.m), [`pe_list_maps.m`](pe_list_maps.m),
  [`pe_map_scalars.m`](pe_map_scalars.m), [`pe_get_mesh.m`](pe_get_mesh.m),
  [`pe_areas_per_interval.m`](pe_areas_per_interval.m),
  [`pe_download_waveform.m`](pe_download_waveform.m) and
  [`pe_to_openep.m`](pe_to_openep.m). They use MATLAB's built-in
  HTTP functions and require no additional toolbox.
- [`pulse_ep_demo.m`](pulse_ep_demo.m) — End-to-end demo: lists
  studies, picks the first map, renders the mesh with `trisurf`,
  and shows a histogram of the per-vertex scalar field.
- [`openep_demo.m`](openep_demo.m) — fetch a map as an
  [OpenEP](https://openep.io) `userdata` structure and print what it holds,
  including the notes on what it could not. OpenEP parses CARTO and Precision
  itself but not EnSite X, so this is what puts EnSite X data inside it. With
  OpenEP on the path, `drawMap(userdata)` carries on from where the demo ends.
  See the [OpenEP guide](../../docs/guides/openep.md).
- [`areas_per_interval.m`](areas_per_interval.m) — call
  `/calculate_areas_for_intervals` and tabulate the surface area
  per score bin — the same reduction the bundled web viewer and the
  clinical Excel reports show, computed by the shared server and displayed in MATLAB.

## What this demonstrates

These demos are the MATLAB-side contribution to the **cross-language
reproducibility statement** of the software paper: the same scalar
histogram from downloaded values and the shared server interval-area
calculation, displayed as a MATLAB table.

## Requirements

- MATLAB R2020a or newer (`webread`/`webwrite` with JSON support).
- No additional toolbox required.

## Run

Set the env vars described in [`../README.md`](../README.md) and start
MATLAB from the **same shell** so it inherits them. Then in MATLAB:

```matlab
cd examples/matlab
pulse_ep_demo
openep_demo        % the OpenEP structure
```

Configure credentials through environment variables or `setenv` in a private
MATLAB session. Keep credentials out of example files.

## Notes

- MATLAB array indexing is 1-based — `pe_get_mesh` returns triangle
  indices already converted from the 0-based JSON payload.
- JSON null scalar entries are converted to MATLAB `NaN`. Missing values
  remain missing; rendering depends on the selected plotting settings.

## Scope of the reproducibility claim

Histograms are calculated in the client from the returned mesh values.
The interval-area examples call the shared server calculation; they do
not independently reimplement surface integration. The default mesh payload uses the API's display representation. Select
`representation=raw` to compute on the original stored geometry.
See [complete analysis export](../../docs/reference/rest-api.md#complete-analysis-export).

## Full analysis data

The API now supports `representation=raw`, including every stored field,
measurement, electrode position, marker, provenance and waveform download links.
R and MATLAB retain the complete response in `data`; ParaView exposes raw
surface fields and a second acquisition-point output. See the
[API contract](../../docs/reference/rest-api.md#complete-analysis-export) for
units, missing values and the distinction between stored and vendor-original data.
