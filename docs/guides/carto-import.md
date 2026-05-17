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
| `*.mesh`            | text mesh         | Triangulated chamber surface (vertices + triangles).     |
| `*.car`             | tabular           | Per-point coordinates and reference electrode positions. |
| `*Eleclectrode_Positions*.txt` | tabular | Reference catheter geometry per point.                   |

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
