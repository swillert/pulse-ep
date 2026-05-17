# pulse-ep + MATLAB

Two files:

- [`pulse_ep_client.m`](pulse_ep_client.m) — REST client built on
  MATLAB's built-in `webread` / `webwrite` (no toolbox required).
  Exports four functions: `pe_login`, `pe_list_studies`,
  `pe_list_maps`, `pe_get_mesh`.
- [`pulse_ep_demo.m`](pulse_ep_demo.m) — End-to-end demo: lists
  studies, picks the first map, renders the mesh with `trisurf`, and
  shows a histogram of the per-vertex scalar field.

## Requirements

- MATLAB R2020a or newer (`webread`/`webwrite` with JSON support).
- No additional toolbox required.

## Run

Set the env vars described in [`../README.md`](../README.md) and start
MATLAB from the **same shell** so it inherits them. Then in MATLAB:

```matlab
cd examples/matlab
pulse_ep_demo
```

If you prefer to hardcode credentials for a one-off run, edit the
`baseURL`, `username`, `password` lines at the top of `pulse_ep_demo.m`.

## Notes

- MATLAB array indexing is 1-based — `pe_get_mesh` returns triangle
  indices already converted from the 0-based JSON payload.
- `NaN` scalars (vertices outside the catheter interpolation radius)
  are passed through to MATLAB unchanged; `trisurf` colors them grey.
