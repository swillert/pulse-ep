# pulse-ep + R

Files in this directory:

- [`pulse_ep_client.R`](pulse_ep_client.R) — a ~80-line REST client
  (login, list studies, list maps, fetch mesh) built on `httr2`.
- [`pulse_ep_demo.R`](pulse_ep_demo.R) — fetch a map, render the
  triangle mesh with `rgl`, plot the per-vertex scalar histogram with
  `ggplot2`.
- [`areas_per_interval.R`](areas_per_interval.R) — call
  `/calculate_areas_for_intervals` and tabulate the surface area per
  score bin — the same per-map reduction the bundled web viewer and the
  clinical Excel reports show, computed independently in R.

## What this demonstrates

These two demos are the R-side contribution to the **cross-language
reproducibility statement** of the software paper: identical platform
reductions (scalar histogram + area-per-interval table) computed in R
from the same REST payload Python, MATLAB and the web viewer consume.
A clinical co-author who works in R should reproduce the same numbers
without a Python install.

The σ-resolution analysis (Heat-Method geodesics + Gaussian fit) is
out of scope here — it is a scientific contribution of
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay) and
has its own cross-language demos there.

## Required R packages

```r
install.packages(c("httr2", "jsonlite", "rgl", "ggplot2", "tibble"))
```

(`rgl` is optional — comment out the 3D plot block in
`pulse_ep_demo.R` if you do not want OpenGL.)

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
