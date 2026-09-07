# Importing EnSite X studies

How an Abbott EnSite X export is decoded, what pulse-ep takes
from it, and how to drive the import — by command line or through the
browser review queue.

## What an export contains

An EnSite X export is a folder (or ZIP of one) of `SJM_DIF_5.0` XML meshes
and DxL CSV tables. pulse-ep reads these:

| File | What it becomes |
| ---- | --------------- |
| `Contact_Mapping_Model*.xml` | An EP map: geometry plus its per-vertex voltage field. |
| `Model_Groups.xml` | Chamber shells, as geometry-only anatomy maps. |
| `difNNN.xml` | The CT segmentation — endocardium, wall-thickness shells, channels, fat infiltration — likewise as anatomy maps. |
| `Contact_Mapping/Map_*.csv` | The map's measurement points, one DxL channel per file. |
| `AutoMark_Data.csv`, `Duo_AutoMarksSummaryList*.csv`, `Lesions.csv`, `Labels.csv` | Placed points: ablations, PFA applications, markers and labels. |
| `*Waveforms*.csv`, `*ECG*.csv` | Signal traces — **opt-in**, see [Waveforms](#waveforms). |

Everything else in the export (patch impedance, system configuration,
respiration traces, notebook logs) is deliberately not imported.

!!! note "Filenames are not trustworthy"

    Operators rename maps by hand, so the same map can arrive as
    `…_RVStimPre-unipolar.xml` and `…_RvStimPre-bipolar.xml`, or with a
    typo like `-bpolar`. Grouping is therefore case-insensitive and the
    polarity suffix is matched tolerantly. If a pair still fails to merge,
    the plan says so rather than silently producing two half-maps.

## bipolar and unipolar are one map

A map's bipolar and unipolar exports are separate files that share
identical geometry. pulse-ep merges them into **one** map carrying both
`voltage_bipolar` and `voltage_unipolar`. If the grouped files turn out
not to share vertices, they are kept separate instead of merged blindly.

## Measurement points

A map exports its point set **once per DxL channel** — the same columns
and the same point ids, with only the value column differing. pulse-ep
merges them back into one set of points, each carrying every measurement:

| `Map type:` | Quantity | Unit |
| ----------- | -------- | ---- |
| `PP_bi` / `PP_uni` / `PP_omni` | `voltage_bipolar` / `voltage_unipolar` | mV |
| `LAT` | `activation_time` | ms |
| `Score` | `map_score` | — |
| `CFEmean` | `cfe_mean` | ms |
| `CFEstdDev` | `cfe_stddev` | ms |
| `Fractionation` | `fractionation` | — |
| `PFreq` | `peak_frequency` | Hz |
| `PNeg` | `voltage_peak_negative` | mV |

A channel this list does not cover is still imported, under the export's
own column name with kind `unknown`, so nothing is lost while the
vocabulary catches up.

!!! warning "`adjTime` is not activation time"

    The `adjTime (ms)` column is the annotation *window offset* and is
    frequently one constant value across an entire export. It is imported
    as `annotation_time`. A map's activation time comes from the `LAT`
    channel.

## Waveforms

Signal traces are **off by default** — they can be larger than the rest
of the export combined. Turn them on explicitly and say where to put
them; they are stored as Parquet outside the database, with only a
reference row in it.

```bash
pulse-ep-import-ensite -i /path/to/export.zip \
    --waveforms --store-dir /var/pulse/waveforms
```

For the [import queue](#the-import-queue), the store location comes from
`PULSE_EP_WAVEFORM_STORE_DIR` instead. Selecting waveforms with no store
configured fails the job **before** anything is written, rather than
quietly dropping the signals.

## Command-line import

```bash
# 1. See what would happen. Writes nothing.
pulse-ep-import-ensite -i /path/to/export.zip --dry-run

# 2. Import it.
pulse-ep-import-ensite -i /path/to/export.zip

# 3. Re-import a study that is already in the database.
pulse-ep-import-ensite -i /path/to/export.zip --clear
```

The input may be a folder or a ZIP. Imports are idempotent by the
export's study GUID: running the same import twice does nothing the
second time unless `--clear` is given.

A dry run prints the plan:

```
study 70538697-25b4-43bd-854c-a9000da6fa96  (vendor=ensite)
  map Contact_Mapping_Model  verts=65739  fields=['voltage_bipolar']  point-files=8
  waveforms: 6 files ~3.3 MB (include=False)
```

Read it before importing an export from a site you have not seen before:
the map count, the vertex counts, the number of point files and any
`issues=[…]` are exactly what the importer will act on.

## The import queue

The import queue supports a review workflow through `/import`:

```
detected → needs_review → importing → done | error
```

1. Copy a complete export folder or `.zip` bundle to `PULSE_EP_DROP_DIR`.
2. Open `/import` and select **Scan drop directory**. The scanner enqueues
   previously unseen paths whose files have been unchanged for at least five
   seconds; scanning is requested explicitly, not run by a background daemon.
3. Prepare the job, inspect the proposed plan, adjust selections and commit.

For automated transfers, finish copying before scanning. Python callers can
use `scan_and_enqueue(..., require_marker=True)` to require a sibling
`<name>.done` completion marker instead of a quiescence interval.

Repeat scans skip already queued paths. Commit checks for existing study
identities; keep the source location stable and avoid concurrent imports of
the same study, because study names are not protected by a uniqueness constraint.

The same lifecycle is available over REST — see
[`/api/import-jobs`](../reference/rest-api.md#import-queue).

## Comparing two maps

Maps in the same coordinate frame can be compared numerically, for example:

```bash
curl -s -X POST "$PULSE_EP_BASE_URL/api/compare" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"map_a_id": 12, "map_b_id": 13,
         "scalar_name": "voltage_bipolar", "metric": "geodesic"}'
```

`euclidean` uses the nearest vertex in space. `geodesic` first places B
vertices on their nearest A vertices, then propagates correspondence along
A's surface. Both require aligned coordinate frames. Initial projection can
still select the wrong surface near folds; neither method performs registration
or establishes biological comparability.

## See also

- [CARTO import guide](carto-import.md) — the other supported vendor.
- [Command-line tools](../reference/cli.md#pulse-ep-import-ensite)
- [Configuration](../getting-started/configuration.md) —
  `PULSE_EP_DROP_DIR`, `PULSE_EP_WAVEFORM_STORE_DIR`.
- [Data model](../reference/data-model.md) — how scalar fields,
  measurement points and placed points are stored.
