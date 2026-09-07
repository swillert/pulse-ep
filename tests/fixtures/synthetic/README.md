# Synthetic exports (CARTO 3 / EnSite X)

Two complete example exports, one per vendor, for checking pulse-ep without
patient data.

```
carto/synthetic_study/    <map>.mesh, Study.xml, <map>_Points_Export.xml
                          + 64 point exports + one electrode position file each
ensite/synthetic_study/   Contact_Mapping_Model.xml (SJM_DIF_5.0)
                          + Contact_Mapping/Map_PP_bi.csv
```

## What they establish — and what they do not

**They establish** that pulse-ep reads both file layouts in full — mesh,
scalar fields, measurement points, electrode geometry — and that the result
carries through to analysis. Both exports contain **the same** synthetic
surface, so the two decode paths are compared against one another by checking
that both readers arrive at the same area.

**They do not establish** that the field meanings are clinically correct.
Whether the column we call `voltage_bipolar` really is the bipolar voltage in
the device cannot be shown by any self-generated dataset — that needs real
exports. The mapping was checked against real studies from both vendors; that
check is not reproducible here.

In short: **format yes, semantics no.**

## Why they are derived from real exports

The files are not invented. `tools/make_synthetic_fixtures.py` reads a real
export, takes over its *structure* — section headers, comment lines, column
sets, number formats — and fills it with generated content. The difference is
not cosmetic: a hand-rebuilt `[VerticesColorsSection]` header had one comment
line too few and three columns instead of thirteen. The reader lost exactly one
row to that — a defect that would have stayed invisible against an invented
fixture.

The header lines taken over are format documentation, not study data. The
generator removes comments referring to the source study, and resets the stored
camera matrix to the identity.

### File names

The names are part of the format, so they match the real ones:
`Contact_Mapping_Model.xml`, `Contact_Mapping/Map_PP_bi.csv`, `<map>.mesh`,
`<map>_Points_Export.xml`, `<map>_P<id>_Point_Export.xml`,
`<map>_<connector>_Eleclectrode_Positions_OnAnnotation_<t>.txt`. The map name
carries spaces and hyphens as in the original (`1-1-1-Synthetic Left Atrium`) —
a name without spaces would exercise a path that real exports do not have.

**One deliberate deviation:** the CARTO study catalogue is named after the
patient and the time of the procedure in the original. That name cannot ship,
so the fixture calls it `Study.xml`. Detection reads the content (`<Study`) and
not the name, so the deviation has no effect — but the fixture does not
exercise catalogue naming either.

## Found along the way

Generating and checking these fixtures turned up real defects:

- The `core` import path returned **no** measurement points at all for CARTO.
  The coordinates live in the study catalogue, not in the point export, and
  only the CLI filled them in afterwards (`fill_positions`).
- CARTO detection passed every point XML on as a study catalogue.

## Usage

```bash
examples/verify.sh                      # check against an installation
pytest tests/test_synthetic_fixtures.py # the same as a test, runs in CI
```

Regenerate (needs real exports, which are not part of this repository):

```bash
python tools/make_synthetic_fixtures.py --ensite <export.zip> --carto <directory>
```

The generator only clears the per-vendor subdirectories — this file stays. It
once fell victim to an `rm -rf` on the parent directory before it had ever been
checked in.
