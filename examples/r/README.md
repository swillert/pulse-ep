# pulse-ep + R

Two files:

- [`pulse_ep_client.R`](pulse_ep_client.R) — a ~80-line REST client
  (login, list studies, list maps, fetch mesh) built on `httr2`.
- [`pulse_ep_demo.R`](pulse_ep_demo.R) — a runnable example: lists the
  studies, picks the first map, renders the triangle mesh with `rgl`,
  and plots the scalar distribution with `ggplot2`.

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

## Scope

These examples stop at "load and display". The Gaussian σ-resolution
analysis (Heat-Method geodesics + non-linear least-squares fit) is a
separate scientific contribution and lives in
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay); see
that repository's `examples/` directory for the corresponding R / Python
walkthroughs.
