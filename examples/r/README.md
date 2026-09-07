# pulse-ep + R

Files in this directory:

- [`pulse_ep_client.R`](pulse_ep_client.R) — a REST client
  (login, list studies, list maps, fetch mesh) built on `httr2`.
- [`pulse_ep_demo.R`](pulse_ep_demo.R) — fetch a map, render the
  triangle mesh with `rgl`, plot the per-vertex scalar histogram with
  `ggplot2`.
- [`areas_per_interval.R`](areas_per_interval.R) — call
  `/calculate_areas_for_intervals` and tabulate the surface area per
  score bin — the same per-map reduction the bundled web viewer and the
  clinical Excel reports show, computed by the shared server and displayed in R.

## What this demonstrates

These two demos are the R-side contribution to the **cross-language
reproducibility statement** of the software paper: identical platform
inputs for a locally computed histogram and a server-computed interval-area
table, using the same API as Python, MATLAB and the web viewer.
A clinical co-author who works in R should reproduce the same numbers
without a Python install.

## Required R packages

```r
install.packages(c("httr2", "jsonlite", "rgl", "ggplot2", "tibble"))
```

The supplied rendering demo loads `rgl`. The area-only example does not
need an OpenGL window. Optional Parquet reading uses the `arrow` package.

## Run

Set the environment variables described in [`../README.md`](../README.md)
in your shell, then:

```bash
cd examples/r

# 1) mesh + histogram
Rscript pulse_ep_demo.R

# 2) area-per-interval table (using the colormap intervals of the platform)
Rscript areas_per_interval.R
```

Both scripts read `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME` and
`PULSE_EP_PASSWORD` from the environment.

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
