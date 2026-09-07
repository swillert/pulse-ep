# pulse-ep + MATLAB

Install the generated `pulse_ep_matlab-VERSION.mltbx` toolbox, or add this
directory to the MATLAB path. See the [MATLAB toolbox guide](../../docs/guides/matlab.md)
for installation, component selection and release verification.

The existing functions remain supported. The optional `pulseep.Client`
remembers the server and login and calls those same functions:

```matlab
pe = pulseep.Client(getenv('PULSE_EP_BASE_URL'));
pe.login(getenv('PULSE_EP_USERNAME'), getenv('PULSE_EP_PASSWORD'));
studies = pe.studies();                 % table
maps = pe.maps(studies.id(1));           % table; check for empty results first
map = pe.loadMap(maps.id(1), 'Include', {'mesh','fields','points'});
```

`pe_load_map` offers the same selection as a direct function. `pe_list_points`
and `pe_list_waveforms` list points and signal metadata without loading a mesh.
`toolbox_demo.m` demonstrates the session interface. `build_toolbox.m`
creates the installer from public source files; packaging requires R2023a+.

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
  including the notes on missing quantities. With OpenEP on the path, run
  `getArea`, `getMeanVoltage`, `getLowVoltageArea` and `drawMap` on that
  object. The demo independently verifies both area results. Geometry-only
  maps skip voltage analysis and render without a scalar field.
  All named surface fields are available in `userdata.surface.signalMaps`
  and point measurements in `userdata.electric.signalProps`, including
  quantities beyond OpenEP's five standard surface columns. Their records
  retain declared kinds and units; surface records also carry validity masks
  and provenance. The guide shows how to plot an additional field in OpenEP.
  See the [OpenEP guide](../../docs/guides/openep.md).
- [`areas_per_interval.m`](areas_per_interval.m) — call
  `/calculate_areas_for_intervals` and tabulate the surface area
  per score bin — the same reduction the bundled web viewer and the
  clinical Excel reports show, computed by the shared server and displayed in MATLAB.
- [`openep_signal_demo.m`](openep_signal_demo.m) — fetch point-linked signals
  via REST, use OpenEP's `getEgmsAtPoints`, and plot the bipolar, both unipolar
  and reference traces with their declared units. Requires `PE_MAP_ID` and
  a map imported with waveform storage enabled.
- [`pe_openep_conduction_velocity.m`](pe_openep_conduction_velocity.m) —
  prepare physical LAT and eligible points for OpenEP's conduction-velocity
  calculation. Handles sample-rate/reference-offset differences and rejects
  pace scores, duplicate coordinates and degenerate point sets.

- `pe_openep_ablation_area(userdata, 'Radius', 5)` — use OpenEP's RF tag
  coverage calculation with explicit handling of zero, one or two markers
  and empty coverage. Requires an explicit RF selection and a mesh.

## What this demonstrates

These demos are the MATLAB-side contribution to the **cross-language
reproducibility statement** of the software paper: the same scalar
histogram from downloaded values and the shared server interval-area
calculation, displayed as a MATLAB table.

## Requirements

- MATLAB R2020a or newer (`webread`/`webwrite` with JSON support).
- The REST client functions need no additional toolbox. To run the OpenEP
  analysis section, install OpenEP separately; some of its functions use the
  Statistics and Machine Learning Toolbox.

## Run

Set the env vars described in [`../README.md`](../README.md) and start
MATLAB from the **same shell** so it inherits them. Then in MATLAB:

```matlab
cd examples/matlab
pulse_ep_demo
run(fullfile(pwd, 'openep_demo.m')) % REST -> userdata -> OpenEP analyses
```

Configure credentials through environment variables or `setenv` in a private
MATLAB session. Keep credentials out of example files.
Use an explicit path for the OpenEP demo because OpenEP itself ships a script
with the same name. See the [OpenEP guide](../../docs/guides/openep.md) for
installation and the inputs required by each analysis.

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
