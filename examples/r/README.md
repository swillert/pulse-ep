# pulse-ep + R

Two files:

- [`pulse_ep_client.R`](pulse_ep_client.R) — a ~80-line REST client
  (login, list studies, list maps, fetch mesh) built on `httr2`.
- [`pulse_ep_demo.R`](pulse_ep_demo.R) — a runnable example: lists the
  studies, picks the first map, renders the triangle mesh with `rgl`,
  plots the scalar distribution with `ggplot2`, and fits a Gaussian
  decay (`A·exp(-d²/(2σ²)) + B`) of the scalar against Euclidean
  distance from the point of maximum value via `nls()`.

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
Rscript pulse_ep_demo.R
```

`pulse_ep_demo.R` reads `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME` and
`PULSE_EP_PASSWORD` from the environment, but you can also pass
explicit values when calling `pe_login()`.

## Note on the σ-fit

The fit in this demo uses **Euclidean** distance from the maximum-scalar
vertex. That is a deliberately simple stand-in for the geodesic
(Heat-Method) distances used by the actual σ-resolution analysis in
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay). The
point here is to show that a third-party stats stack (R + `nls`)
operating on raw mesh data reaches a σ close to what the Python
pipeline computes — i.e. the published values are not Python-specific
artefacts.
