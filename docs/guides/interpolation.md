# What a vertex shows: masking vs. interpolating

A map is measured at a few thousand points and displayed on a mesh of tens of
thousands of vertices. Something has to decide what every other vertex shows,
and pulse-ep now offers both answers.

## The two answers

=== "Mask (default)"

    Keep the vendor's own per-vertex field and hide the vertices too far from
    any real measurement.

    ```python
    mesh, values = epmap.interpolate_scalar_values(
        epmap.get_scalar("activation_time"),
        distance_threshold=7.0,          # mm
    )
    ```

    CARTO and EnSiteX both write an interpolated value per vertex; this shows
    it, with a confidence mask over it. Despite the method's name, nothing is
    interpolated here — and this is exactly what the method always did.

=== "Compute it"

    Recompute the field from this map's measurement points, so the result
    follows from the raw data instead of the acquisition system's own
    (undocumented, version-dependent) interpolation.

    ```python
    mesh, values = epmap.interpolate_scalar_values(
        epmap.get_scalar("activation_time"),
        method="geodesic",               # or "gaussian"
        sigma=3.0,                       # kernel width in mm
        distance_threshold=7.0,
    )
    ```

    Use this when the result has to be reproducible from the export, when you
    want a kernel width of your choosing, or when the vendor's field is
    unavailable — for example on a map assembled from re-annotated points.

## Straight-line or along the surface

`gaussian` weights each measurement by straight-line distance. It is fast, and
it is wrong wherever the surface folds back on itself: across a thin wall, at
a ridge, in the ostium of a vein, a point can be a millimetre away through
blood and centimetres away along tissue. Straight-line weighting then paints
one side's values onto the other.

`geodesic` measures along the surface instead, so a value only spreads as far
as the tissue carries it.

```python
from pulse_ep.core.interpolation import gaussian_interpolate, heat_interpolate
```

Geodesic weighting uses the **heat kernel**: heat diffused on a surface for a
time `t` arrives with weight `exp(-d²/4t)` in the *geodesic* distance `d`
(Varadhan's formula — the identity the Heat Method in
`pulse_ep.core.geodesic` already rests on). Diffusing the measured values and
diffusing an indicator of where measurements exist, then dividing, is
therefore exactly a geodesic Gaussian-weighted average — in two sparse solves
rather than one distance field per measurement point. On a 13 500-vertex
CARTO map with 2 000 points it takes about 0.15 s.

## Cyclic maps: early meets late

Averaging activation times across the wrap-around of a reentrant circuit is
meaningless. In a 300 ms tachycardia, 5 ms and 295 ms are 10 ms apart in the
patient; their arithmetic mean is 150 ms — the far side of the circuit, drawn
as a line of block straight through the wavefront.

```python
mesh, values = epmap.interpolate_scalar_values(
    epmap.get_scalar("activation_time"),
    method="geodesic",
    cycle_length=0,      # 0 = infer it from the data (max - min)
)
```

With `cycle_length` the values are carried onto the unit circle, interpolated
there, and brought back, so late meets early the way it does in the patient.
Use it for reentrant activation maps; leave it off for voltage, force or
anything else that does not wrap.

## What the options do not change

- **The confidence mask is orthogonal.** `distance_threshold` still hides
  vertices with no measurement in reach, whichever method computed the value
  — measured geodesically when the method is `geodesic`, so the boundary of
  the shown region follows the tissue rather than the air gap.
- **An unmeasured point is not a zero.** Points carrying no value for the
  requested quantity are dropped before interpolation, not counted as zero.
- **A computed method needs measurements.** On a map whose points do not carry
  the quantity — an anatomy-only mesh, or a per-vertex field with no point
  data behind it — the computed methods raise rather than invent a field.
  `method="mask"` is the answer there.
