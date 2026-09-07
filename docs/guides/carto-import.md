# Importing CARTO studies

This guide explains what a CARTO 3 export looks like, what
[`pulse-ep-import-carto`](../reference/cli.md#pulse-ep-import-carto) does with it, and how
to drive batch imports from a study CSV.

## What is a CARTO 3 export?

When an electrophysiology recording is exported from the CARTO 3 mapping
system (Biosense Webster / Johnson & Johnson) it is a directory tree
containing per-study XML manifests, per-map mesh files, per-point catheter
geometry, and tabular signal data.

For pulse-ep the relevant artefacts are:

| Artefact            | Format            | Purpose                                                  |
| ------------------- | ----------------- | -------------------------------------------------------- |
| `Study_*.xml`       | XML               | Patient/study metadata, list of EP maps.                 |
| `Map_*.xml`         | XML               | Per-map metadata, list of points, colormap references.   |
| `*.mesh`            | text mesh         | Triangulated chamber surface (vertices + triangles + per-vertex columns). |
| `*.car`             | tabular           | Per-point coordinates and reference electrode positions. |
| `*Eleclectrode_Positions*.txt` | tabular | Reference catheter geometry per point.                   |
| `*_ECG_Export_*.txt` | tabular          | One 2.5 s signal window per acquired point — **opt-in**, see [Signals](#signals-the-per-point-ecg-windows). |

pulse-ep does not require you to know the format details — the importer
parses everything and writes structured records into the relational
database.

## Single-study import

```bash
pulse-ep-import-carto /path/to/study-export.zip
```

You can also pass an unpacked directory:

```bash
pulse-ep-import-carto /path/to/study-export/
```

The importer:

1. Auto-detects whether the path is a zip archive or a directory.
2. Parses the `Study_*.xml` manifest, extracting patient ID, study name,
   creation date, mapping catheter, anatomical region (atrium).
3. For each `Map_*.xml` listed in the study: parses metadata, loads the
   referenced `.mesh` file, attaches the per-point `.car` table.
4. Writes the data into a `StudyModel` + `EPMapModel` + `EPMapPoint`
   tree via the SQLAlchemy ORM.

Use `--help` for the full flag list:

```bash
pulse-ep-import-carto --help
```

## Idempotency

Re-importing the same study is safe: existing records with the same
`study_name + map_name` keys are detected and the importer either
updates them in place or skips, depending on the `--on-conflict` flag.
The default behaviour is `skip`, which is appropriate for CI pipelines
that re-run the import nightly.

## Batch imports from a CSV

For research workflows with many studies, write a `studies.csv` like:

```csv
study_path,atrium,operator,notes
/data/uksh/2024/study_01.zip,LA,sw,AF first pass
/data/uksh/2024/study_02.zip,LA,sw,AF redo
/data/uksh/2024/study_03/,RA,el,atrial flutter
```

Then drive the importer from Python:

```python
from pathlib import Path
from pulse_ep.core.importer import (
    get_filenames_from_csv,
    import_studies,
)

paths, attributes = get_filenames_from_csv(Path("studies.csv"))
import_studies(paths, attributes)
```

`import_studies` ingests each row with the same idempotency guarantees
as the single-study command, and additionally attaches the CSV-row
attributes (`atrium`, `operator`, `notes`, …) to the resulting
`EPMapAttributes` records so they are queryable through the REST API.

## Tagging pace-maps

Pace-mapping similarity scores are the central quantity of the
σ-resolution research. After import, mark the relevant maps as
pace-maps with [`pulse-ep-tag-maps`](../reference/cli.md#pulse-ep-tag-maps):

```bash
pulse-ep-tag-maps --pacemap 12 13 14 15
```

This sets the `pacemap=true` attribute on the listed map IDs, which the
viewer renders with a distinct icon and the REST `filter_by_attributes`
endpoint can then query.

Inspect existing tags:

```bash
pulse-ep-tag-maps --list
```

## Verifying an import

Three quick checks after a fresh import:

=== "CLI"

    ```bash
    pulse-ep-check-mesh --study "AF-2024-01"
    ```

    Reports vertex / triangle counts and flags meshes with non-manifold
    edges or duplicate triangles.

=== "REST"

    ```bash
    curl -s "$PULSE_EP_BASE_URL/list_studies" \
        -H "Authorization: Bearer $TOKEN" | python -m json.tool
    ```

=== "Python"

    ```python
    from pulse_ep import get_db_session, StudyModel

    with get_db_session() as s:
        for study in s.query(StudyModel).all():
            print(study.id, study.study_name, len(study.maps))
    ```

## Extracting meshes for offline analysis

The [`pulse-ep-extract-meshes`](../reference/cli.md#pulse-ep-extract-meshes)
CLI walks the database and dumps each EPMap as an NPZ file
(`vertices`, `triangles`, `scores`, `point_coordinates`), suitable for
external scientific pipelines that take NumPy arrays.

```bash
pulse-ep-extract-meshes --output /tmp/extracted/
```

## Troubleshooting

??? failure "`KeyError: 'CartoSystem'` when parsing a Study_*.xml"

    The export is from a CARTO 3 version pulse-ep has not been tested
    against. Open an issue with the XML snippet (patient data removed).
    The XML parser lives in `pulse_ep.core.xml_proc` and is the right
    place to add a new schema variant.

??? failure "Mesh file is empty after extraction"

    Some clinical exports include encrypted mesh archives. pulse-ep
    detects and skips these with a warning. Check that
    `chardet.detect()` reports a sensible encoding on the file before
    blaming pulse-ep.

??? failure "Import succeeds but the viewer shows no scalars"

    Run `pulse-ep-populate-colormaps` once after the first import — the
    colormaps table needs initial rows so the viewer knows how to color
    the scalar field. This is a one-time bootstrap, not per-study.

## See also

- [REST API reference](../reference/rest-api.md) — querying imported
  studies and maps.
- [Data model](../reference/data-model.md) — the ORM tables the importer
  writes to.
- [CLI reference: `pulse-ep-import-carto`](../reference/cli.md#pulse-ep-import-carto)
  — full flag listing.

## Archive format

CARTO exports are frequently **7-Zip archives named `.zip`**. pulse-ep detects
the container by its content signature rather than its suffix, so such an
export imports without renaming — but reading it needs the optional `py7zr`
package:

```bash
pip install "pulse-ep[sevenzip]"
```

Without it, a 7-Zip export raises a message naming the missing package rather
than failing obscurely.

## What the mesh carries

A `.mesh` file names its own per-vertex columns in the
`[VerticesColorsSection]` header. Every column that holds data is imported
under the quantity it names:

| Column | Imported as |
| ------ | ----------- |
| `Unipolar` / `Bipolar` | `voltage_unipolar` / `voltage_bipolar` |
| `LAT` | `activation_time` — or `pacemap_score`, when the slot holds an entirely negative pace-match correlation (CARTO overloads it) |
| `Paso` | `pacemap_score` |
| `Impedance` / `Force` | `impedance` / `contact_force` |
| `µBi` | `voltage_bipolar_micro` — micro-electrode bipolar amplitude, a different quantity from the electrode-pair one |
| `A1`, `A2`, `A2-A1`, `SCI`, `ICL`, `ACL` | kept under their raw CARTO names: they are real quantities whose exact semantics are not established here, and a guessed label on a clinical measurement is worse than an unfamiliar one |
| `EML`, `ExtEML`, `SCAR` (`[VerticesAttributesSection]`) | kept under their raw names, and only where something is actually marked |

Most exports fill only three or four of the thirteen colour columns; the
empty ones are not registered, so a map advertises the quantities it really
measured.

!!! note "Column *names*, not positions"

    Until 0.2.4 the reader took columns by position, which dropped `Paso`,
    `µBi` and the whole attributes section, and would have mis-assigned every
    quantity in an export that ordered them differently.

## What a point carries

Every acquired point (`<map>_Points_Export.xml` + `<map>_P<n>_Point_Export.xml`)
becomes a vendor-neutral measurement point with its position from the study
catalogue, `voltage_unipolar` / `voltage_bipolar`, its catheter electrodes,
and the quantity CARTO stores as the annotation difference
`Map_Annotation - Reference_Annotation`:

| The map's `LAT` slot holds | The point's annotation difference is imported as |
| -------------------------- | ------------------------------------------------- |
| an activation time | `activation_time` (ms) |
| a pace-match score (`pacemap_score`) | `pacemap_score` (%) — the **per-site score the operator saw**, stored with the same negative sign as the mesh; `-10000` (the reference beat itself, which is never scored) and values that are no percentage (a point annotated in another mode) are omitted |

The points follow the mesh's verdict on what the slot holds, so a map and its
points never disagree. This is the measurement the interpolated per-vertex
field is built from; sampling the vertex field at a point's position returns
the vendor's interpolation, not the point's own score (in one reference study
21 % of the points differed by more than two points, up to fifty).

!!! warning "An export that writes the scores without the sign"

    One study wrote its pace-match scores as positive values (54 … 96). Such
    a map cannot be told from an activation map by the data alone; it is
    imported as one, and its points carry `activation_time`. Mark it with the
    `pacemap` attribute (see [Tagging pace-maps](#tagging-pace-maps)) and
    read the points' values as scores.

Beside that value the point keeps the **components it was derived from**, as
`annotations`:

```json
{"start_time": 13500280, "reference": 2000, "map": 1904,
 "woi_from": -170, "woi_to": 129}
```

The first sample of the recorded window on the study clock, the reference and
mapping annotations as offsets into it, and the window of interest. They are
what tells a reader where in a 2.5 s signal window to look — a stored waveform
records the same facts under the same names, so a point and its window agree
by construction. Until now they survived only in the CARTO-shaped legacy table
`ep_map_points`, which only `pulse-ep-import-carto` writes; a study imported
through the drop directory had them nowhere.

Points also carry their **tags** — `Location Only` on the reference beat of a
pace map, `Scar`, `His`, or a study's own labels — as names resolved through
the study's `TagsTable`, in `MeasurementPoint.tags` /
`measurement_points.tags`.

## Signals: the per-point ECG windows

CARTO writes one `*_ECG_Export_<timestamp>.txt` per acquired point: 2500
samples at 1 kHz of every recorded channel — surface leads, coronary sinus,
mapping electrodes and the derived bipoles — as raw counts with a single gain
factor in the header.

```bash
pulse-ep-import-carto -i /data/carto-export \
    --waveforms --store-dir /var/pulse/waveforms
```

They are **opt-in**, and for a good reason: a study with a few thousand
points carries several gigabytes of them, more than the rest of the export
together. As Parquet in the waveform store they compress about twentyfold.

Samples are converted to millivolts on import (the header's gain is applied,
so a stored waveform is in a physical unit), timestamped on the study clock so
windows from different points share one axis, and each window keeps what makes
it readable rather than 78 anonymous traces:

- the points it was acquired at (`waveforms.point_source_id`, one row per
  point),
- which channels each of those points was annotated on —
  `UnipolarMappingChannel`, `BipolarMappingChannel`, `ReferenceChannel` from
  the point XML,
- the annotations themselves (reference, map, window of interest).

!!! note "A window belongs to several points"

    A multi-electrode catheter acquires many points from one 2.5 s recording,
    and each of them references the same file. In the export this was
    developed against, **1934 points share 699 windows** — 84 % of points in
    groups of up to ten. The samples are therefore stored once per window and
    every point taken from it gets its own row pointing at that copy, so
    "the signal at point 37" resolves for all of them.

Through the [import queue](../reference/rest-api.md) the same files appear in
the plan as a waveform selection a reviewer can switch on, exactly like
EnSiteX signals.

## Ablation sites (VisiTag)

!!! warning "Unverified — confirm before relying on it"

    The VisiTag parser has **never been tested against a real VisiTag
    export**; no sample was available when it was written. It is built from
    the documented layout and is deliberately defensive, but the ablation
    sites it produces must be checked against the mapping system before they
    are used for anything.

VisiTag is a **separately selected** part of a CARTO export. A bundle exported
without it contains no ablation sites at all — not an empty set, but nothing
to read. If your export has none, re-export from CARTO with VisiTag enabled.

When present, sites are read from the VisiTag `Sites` table into
study-level placed points of type `ablation`, carrying whatever RF parameters
the table holds:

| Column | Attribute |
| ------ | --------- |
| `X`, `Y`, `Z` | position |
| `DurationTime` | `duration_s` |
| `AverageForce` | `average_force_g` |
| `FTI` | `force_time_integral` |
| `MaxTemperature` / `MaxPower` | `max_temperature_c` / `max_power_w` |
| `BaseImpedance` / `ImpedanceDrop` | `base_impedance_ohm` / `impedance_drop_ohm` |
| `RFIndex` / `AblationIndex` / `LesionIndex` | `rf_index` / `ablation_index` / `lesion_index` |

Columns are matched **by name**, case- and separator-insensitively — never by
position, since VisiTag's column set varies between CARTO versions. A column
that is not listed is still kept, under its own name. A table with no
recognisable `X`/`Y`/`Z` yields **no points at all** rather than guesses, and
the import plan flags the file so a reviewer sees the warning.

## Tags in the study XML

The study catalogue contains a `TagsTable` — the *definitions* of the tag
types available in that study (`ABL`/Ablation, `HIS`/His, `PS`/Pacing Site,
…), with ids and colours. These are a palette, not placements: actual tag
placements appear inside a point's `<Tags>` element, which is empty in an
untagged study. Placements are imported as the names of the tags on each
measurement point (`MeasurementPoint.tags`, see
[What a point carries](#what-a-point-carries)); ids the table does not define
are kept as their number. `Anatomical_Tag` entries are region outlines
(`Perimiter`/`LINE_LOOP`), a different concept from placed points, and are
not imported yet.
