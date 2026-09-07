# The web viewer

The bundled Three.js viewer opens stored maps in a browser and uses the same
JWT-authenticated REST API as the external clients. Start the configured
service, open `http://127.0.0.1:5000` and log in with a pulse-ep account.

## Inspect a map

Select a study and map in the dashboard. Choose a scalar from the fields that
map actually contains, such as `voltage_bipolar`, `activation_time` or
`pacemap_score`. Rotate, pan and zoom the surface, and show measurement-point
overlays using the viewer controls. No separate analysis application is needed.

The viewer requests the **display** mesh, which can be repaired, simplified
and masked by measurement distance. It does not display the untouched stored
mesh used by raw API clients. The distance setting controls masking around
measurement positions, not a choice of interpolation method.

## Colormaps and surface areas

Choose a saved colormap and adjust display settings. Administrators can add
or edit colour stops and their numeric positions in the colormap form, then
press **Save** to persist the definition. There is no drag-to-save colourbar.

The viewer sends adjacent numeric colormap intervals to the shared
`/calculate_areas_for_intervals` operation and displays the returned areas
beside the mesh. Areas are in cm² and use unsimplified geometry. For basic
bipolar-voltage analysis, choose `voltage_bipolar` and an absolute scale such
as `viridis_0_3_mV`. Relative display normalisation changes the colours; it
does not rescale the numeric interval request. Use absolute intervals when
interpreting the displayed area table in physical units.

Missing scalar values are grey. Out-of-range finite values use endpoint
colours when clipping is enabled and white when it is disabled.

## Data management and reports

The data manager supports selecting maps by stored attributes. Selected maps
can be added to report configurations. A report stores map IDs, scalar,
distance and colormap settings; Excel generation runs in a background thread.
The report interface can request generation, display status and download the
result. It does not save a screenshot or camera state as a report.

Roles are enforced by the service: `readonly` can retrieve data and calculate
areas, `user` can additionally import and manage reports, and `admin` can
change map attributes and colormaps. Some controls may remain visible even
when a role cannot perform the underlying action.

## Troubleshooting

- **No studies:** check that imports completed and the catalogue request
  succeeds. Accounts share database-wide study access.
- **Missing colours:** check the available scalar fields, selected range and
  measurement-distance mask; seed the default colormaps if needed.
- **Blank 3D view:** check browser WebGL support and hardware acceleration.
- **Expired login:** sign in again to obtain a new JWT.

See [Colormaps and reports](colormaps-and-reports.md), [Managing users](managing-users.md)
and the [REST API reference](../reference/rest-api.md).
