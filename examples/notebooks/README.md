# pulse-ep + Jupyter

[`01_explore_a_study.ipynb`](01_explore_a_study.ipynb) is a self-contained
walkthrough: log in to a running `pulse-ep` server, browse studies and
maps, fetch one map's mesh, render it in 3D with PyVista, and plot the
per-vertex scalar distribution with matplotlib.

## Requirements

```bash
pip install jupyterlab nbconvert ipykernel requests pyvista matplotlib pandas
```

The supplied notebook uses `pl.show(jupyter_backend="static")` for an inline
image. Rendering requires a working VTK off-screen backend. For an interactive
view, additionally install `"pyvista[jupyter]"` and select the `trame` backend.

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
5. Visualisation: inline 3D rendering and scalar histogram.
6. Area-per-interval breakdown via `/calculate_areas_for_intervals`,
   the same reduction the bundled web viewer and the clinical Excel
   reports show — computed here as a `pandas` DataFrame.

Together with the R and MATLAB demos this notebook contributes to the
**cross-language reproducibility statement of the software paper**:
a histogram computed from downloaded values and the common server
interval-area response presented as a local table.

## Scope of the reproducibility claim

Histograms are calculated in the client from the returned mesh values.
The interval-area examples call the shared server calculation; they do
not independently reimplement surface integration. The default mesh payload uses the repaired/simplified display representation.
Select `representation=raw` to obtain the original stored geometry and every
field for independent computations. The API documentation describes metadata,
measurement points and authenticated waveform downloads.
