# OpenEP export

[OpenEP](https://openep.io) is a MATLAB platform for electroanatomic mapping
research. Its analysis functions take one structure, `userdata`, and it parses
CARTO and Precision itself.

What it does not parse is **EnSite X**. That is the reason this exists: a map
that pulse-ep imported — from either vendor — becomes a `userdata`, and any
OpenEP analysis then runs on it.

```matlab
token    = pe_login("http://localhost:5000", "user", "pw");
userdata = pe_to_openep("http://localhost:5000", token, 12);
```

MATLAB reads `GET /epmaps/<id>/openep` and is a client of this API like the
viewer and the other example scripts — no database credential, and no file
handed over out of band.

For a bulk export on the machine that holds the database there is also

```bash
pulse-ep-export-openep --map-id 12 -o map12.mat
```

which writes the same structure as a `.mat`.

Both go through one mapping, on the Python side, where tests pin it — no CI
runs MATLAB, so the part that decides anything should not live there. What is
left for MATLAB is what JSON and `.mat` cannot express: matrices arrive as
nested arrays, and `surface.triRep` has to become a `triangulation` object.

## What maps across

| pulse-ep | `userdata` |
| --- | --- |
| `vertices`, `triangles` | `surface.triRep.X`, `.Triangulation` (1-based) |
| `is_vertex_at_edge` | `surface.isVertexAtRim` |
| `activation_time`, `voltage_bipolar` | `surface.act_bip` (columns 1, 2) |
| `voltage_unipolar`, `impedance`, `contact_force` | `surface.uni_imp_frc` (columns 1–3) |
| `MeasurementPoint.position` | `electric.egmX` |
| `.source_id`, `.tags` | `electric.names`, `.tags` |
| `.measurements` | `electric.voltages.bipolar` / `.unipolar` |
| `.annotations` | `electric.annotations.referenceAnnot` / `.mapAnnot` / `.woi` |
| `.electrodes` | `electric.electrodeNames_bip` |
| computed | `electric.egmSurfX`, `.barDirection` |

The annotation components line up without interpretation, because both sides
record the same thing: where a beat sits in the window recorded for it.

## Read the notes

`userdata.notes` says what the structure could not carry, and
`pulse-ep-export-openep` prints the same lines. Three kinds of entry appear:

- **An empty slot.** OpenEP's surface has four; a map that never measured
  impedance leaves that column NaN.
- **A quantity with nowhere to go.** `cfe_mean`, `fractionation`,
  `pacemap_score` and the rest have no slot at all. They are named in the
  notes rather than dropped in silence.
- **A pace map's score.** This one matters.

!!! danger "A pace map is not written as an activation map"

    CARTO stores the activation time and the pace-match score in the same
    slot, and pulse-ep learned to tell them apart — that is what the declared
    `kind` is for. `userdata.surface.act_bip(:,1)` is positional: OpenEP reads
    it *as* an activation time, because that is where an activation time goes.

    Writing a `pacemap_score` there would tell OpenEP the map is an activation
    map, and every isochrone and conduction-velocity function downstream would
    agree — silently, and wrongly. So the column stays NaN and the note says
    why. A gap can be seen; a plausible wrong number cannot.

    This is the price of the direction. pulse-ep has semantics and OpenEP has
    positions, so the export can only lose meaning, never gain it. What it can
    do is refuse to invent any.

## What is not exported

- **Electrograms.** They live outside the database as Parquet and can dwarf
  everything else, which is why importing them is opt-in too. `electric.egm`,
  `.egmUni` and `.egmRef` are left out.
- **Ablation data.** `userdata.rf` stays empty. VisiTag sites and EnSite X
  lesions are imported onto the *study*, and which map each belongs to is not
  something the exports say — so filling it would mean guessing.

## Licence

The format knowledge here comes from reading
[`importcarto_mem.m`](https://github.com/openep/openep-core) in openep-core,
which is Apache-2.0. No code is taken from it, and none from
[openep-py](https://github.com/openep/openep-py), which is GPL-3.0 and so
cannot be reused in an MIT package — the same line drawn for `carto-reader`.

If you use OpenEP, cite it:
[Williams *et al.*, Front. Physiol. 2021](https://www.frontiersin.org/articles/10.3389/fphys.2021.646023/full).
