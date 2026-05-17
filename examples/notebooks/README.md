# pulse-ep + Jupyter

[`01_explore_a_study.ipynb`](01_explore_a_study.ipynb) is a self-contained
walkthrough: log in to a running `pulse-ep` server, browse studies and
maps, fetch one map's mesh, render it in 3D with PyVista, and plot the
per-vertex scalar distribution with matplotlib.

## Requirements

```bash
pip install jupyterlab requests pyvista matplotlib pandas
```

PyVista's notebook backend uses Trame; in JupyterLab everything renders
inline. On a headless server use the static `panel`/`server` backends or
fall back to matplotlib.

## Run

Set the env vars from [`../README.md`](../README.md), then:

```bash
jupyter lab examples/notebooks/01_explore_a_study.ipynb
```

Or convert and execute non-interactively (useful for CI smoke tests):

```bash
jupyter nbconvert --to notebook --execute \
    examples/notebooks/01_explore_a_study.ipynb \
    --output 01_explore_a_study.executed.ipynb
```

## What the notebook covers

1. Configuration: read connection details from environment variables.
2. Authentication: exchange username/password for a JWT.
3. Catalogue: list studies and maps as `pandas` DataFrames.
4. Mesh: fetch `/get_mesh_data` and build a PyVista `PolyData`.
5. Visualisation: interactive 3D render + scalar histogram.

The Gaussian σ-resolution analysis (Heat-Method geodesics + curve fit)
is intentionally out of scope here — it is a scientific contribution
of the companion package
[`pulse-ep-decay`](https://gitlab.willert.net/sw/pulse-ep-decay) and
has its own notebook walkthrough there.
