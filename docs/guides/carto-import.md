# Importing CARTO 3 studies

pulse-ep reads Biosense Webster CARTO 3 study exports containing a study
catalogue, anatomical meshes and per-point files. Keep the export's directory
structure and related files together; a mesh alone does not contain all
acquisition measurements or signal references.

## What is imported

- The study XML identifies maps, reported point counts, acquisition coordinates
  and point tags.
- `.mesh` files provide geometry and named per-vertex quantities. The importer
  removes unused vertices and triangles and conditions missing-value sentinels.
- Per-point XML and electrode-position files provide available point measurements,
  channel assignments, timing annotations and catheter electrode coordinates.
- Per-point ECG text exports can be imported separately as Parquet signals.
- VisiTag files can be selected in the review workflow, but their parser remains
  unverified against a real VisiTag export.

This is a structured research import, not a lossless copy of every vendor file.
The raw API returns the stored, importer-conditioned data. Coordinates and
stored triangle areas use mm and mm²; area calculations return cm².

## Command-line import

From a configured installation with PostgreSQL running:

```bash
pulse-ep-import-carto -i /path/to/carto-export.zip --dry-run
pulse-ep-import-carto -i /path/to/carto-export.zip --progress
```

Input may be a directory, ZIP or 7-Zip archive. Detection uses archive content,
so a 7-Zip file named `.zip` is supported with the `sevenzip` extra installed.
The dry run discovers studies and lists candidate maps and point counts. It
neither writes the database nor fully validates every mesh and recording.

Maps with fewer than five reported points are skipped. Restrict map names
with a case-insensitive regular expression:

```bash
pulse-ep-import-carto -i /path/to/unpacked-export --map-filter 'PaceMap|LAT'
```

`--pattern` changes the study-XML discovery pattern; `--no-recursive` disables
recursive discovery. Use `--help` for the complete command options.

Existing map names in the same identified study are skipped. CARTO study
identity includes source-path context, so repeated imports from temporary
archive-extraction directories need not resolve to the same study. For repeat
imports, unpack once into a fixed directory and keep that path stable.

**`--clear` drops and recreates all application tables**, including users,
reports and studies from both vendors. It is a whole-database reset, not a
single-study replacement option. It does not remove external Parquet files.

## Named quantities and interpretation

Populated columns such as `Bipolar`, `Unipolar` and `Paso` become named fields
with units and source-column provenance. Unknown populated columns retain
the vendor token and kind `unknown`; entirely missing columns are omitted.
Values whose absolute magnitude reaches the CARTO missing-data sentinel are excluded.

The overloaded `LAT` column needs special care. The reader infers a
pace-mapping score when all valid LAT values lie in [-100, 0], with at least
one negative value, and changes its sign. Values outside that range retain
the activation-time interpretation, including entirely negative times. An explicit score
column such as `Paso` is identified separately. An activation map
whose times all lie in [-100, 0] can still be ambiguous. Check the quantity,
sign and source provenance against the acquisition system before analysis.
Shared field names do not validate a map's clinical interpretation.

## Optional signals

```bash
pulse-ep-import-carto -i /path/to/unpacked-export \
  --waveforms --store-dir /var/pulse/waveforms
```

`--waveforms` requires `--store-dir`. The importer applies the exported gain
and retains available sampling, channel and annotation metadata. Signals are
stored outside PostgreSQL; database rows link them to their source points.
Set `PULSE_EP_WAVEFORM_STORE_DIR` on the service to the same directory so that
clients can download them. Back up both the database and this store.

See the [point-linked waveform example](https://github.com/swillert/pulse-ep/blob/main/examples/python/README.md).

## Review through the import queue

1. Copy a complete export folder or archive to `PULSE_EP_DROP_DIR`.
2. Open `/import` and request **Scan drop directory** after the files have
   stopped changing for at least five seconds.
3. Prepare the job, inspect its study and map selection, then commit it.

The CARTO preparation step reads the study catalogue. Unlike EnSite X
preparation, it does not decode mesh fields in advance; an import plan is
not a complete validation of all export contents. Waveforms are opt-in and
require `PULSE_EP_WAVEFORM_STORE_DIR` on the service. The scanner runs on
request, not as an unattended background daemon.

Python applications use the same `prepare_plan` / `commit_plan` interface.
Avoid concurrent imports of the same study; study-name uniqueness is checked
by application code rather than a database constraint.

## Distributable example

```bash
pulse-ep-import-carto -i tests/fixtures/synthetic/carto/synthetic_study --dry-run
pulse-ep-import-carto -i tests/fixtures/synthetic/carto/synthetic_study
```

This fixture contains 962 vertices, 1,920 triangles and 64 measurement points.
Its geometry and values are generated, and it contains no clinical recordings.
See the [fixture scope](https://github.com/swillert/pulse-ep/blob/main/tests/fixtures/synthetic/README.md),
[EnSite X guide](ensite-import.md) and [REST API reference](../reference/rest-api.md).
