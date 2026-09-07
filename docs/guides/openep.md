# OpenEP export

[OpenEP](https://openep.io) is a MATLAB platform for electroanatomic mapping
research. Its analysis functions take one structure, `userdata`, and it parses
CARTO and Precision itself. This bridge provides database-backed access to
maps imported by pulse-ep from CARTO or EnSite X, through REST or a MATLAB
file. Available quantities determine which OpenEP analyses can run.

```matlab
token    = pe_login("http://localhost:5000", "user", "pw");
userdata = pe_to_openep("http://localhost:5000", token, 12);
```

MATLAB reads `GET /epmaps/<id>/openep` and is a client of this API like the
viewer and the other example scripts — no database credential, and no file
handed over out of band.

## Analyse the object in OpenEP

Install the MATLAB library using the [OpenEP instructions](https://openep.io/documentation/)
(`openep-core`, `develop` branch) and add it to the MATLAB path. For a map
carrying bipolar voltage and measurement points:

```matlab
addpath(genpath('/path/to/openep-core'));
addpath('/path/to/pulse-ep/examples/matlab');
token = pe_login("http://localhost:5000", "user", "pw");
userdata = pe_to_openep("http://localhost:5000", token, 12);
area_cm2 = getArea(userdata);
mean_bipolar_mV = getMeanVoltage(userdata);
low_voltage_cm2 = getLowVoltageArea(userdata, 'threshold', [0 0.5]);
drawMap(userdata, 'type', 'bip');
```

These are OpenEP functions operating on the REST response. `getArea` sums
the original mesh triangles without filling openings. `getMeanVoltage`
returns the arithmetic mean of the finite vertex voltages, not an
area-weighted mean. `getLowVoltageArea` selects whole triangles whose mean
vertex voltage is strictly between the two thresholds; it does not subdivide
triangles at the threshold.

The bundled demo runs these analyses and independently checks both areas:

```matlab
run('/path/to/pulse-ep/examples/matlab/openep_demo.m');
```

Set `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME`, `PULSE_EP_PASSWORD` and optionally
`PE_MAP_ID` before running the demo. Use the explicit script path because
OpenEP also ships an `openep_demo.m`.
The REST client needs base MATLAB; OpenEP analyses may additionally use the
Statistics and Machine Learning Toolbox (`nanmean`, `knnsearch`).

### Analysis limits

- A geometry-only map supports `getArea` and `drawMap(userdata, 'type', 'none')`.
  Missing voltage or activation-time fields remain NaN.
- Keep `includePoints=true` for coloured `drawMap` output. OpenEP uses the
  measurement-point locations to mask regions beyond its distance threshold
  (10 mm by default). The surface-based area functions do not apply this
  display mask, so a grey region in the plot is still part of the mesh area.
- EnSite X point exports supply LAT and left/right curtains in milliseconds.
  With DxL waveforms, the zero-based reference tick is converted to a MATLAB
  sample index and LAT/curtains are converted using the recorded sample rate.
  Without a linked reference tick, a zero origin encodes LAT only; it cannot
  identify a sample in a waveform. Older imports need reimporting to obtain
  the additional timing and point/group links.
- Signal and ablation export are optional; the requested inputs must have
  been imported. Continuous recordings without point/channel links remain
  available through the waveform API but are not guessed into OpenEP points.
- Coordinates are passed through unchanged. OpenEP's AP/PA camera presets
  are not a vendor-independent anatomical registration.

### Compatibility coverage

The bridge targets the [OpenEP data format](https://openep.io/data/).
Native MATLAB checks used R2026a and unmodified `openep-core` revision
`c80852140349cec77ff7964bcf7945aaf0b737d7` (`develop`). They establish the
following coverage, not compatibility with every OpenEP function or release.

| Workflow | Coverage |
| --- | --- |
| Mesh geometry, surface area, anatomy display | Verified with CARTO and EnSite X imports, including geometry-only maps |
| Surface voltage, mean voltage, low-voltage area | Verified with `getMeanVoltage`, `getLowVoltageArea` and `drawMap` |
| Point-based voltage interpolation | Verified with `generateInterpData(..., 'bip-map')` on an EnSite X electrical map |
| Pace-map display and point scores | Verified with negative-score encoding; these values are not physiological activation times |
| Additional surface fields and point properties | Preserved by name in `signalMaps` and `signalProps`; REST/file parity and custom surface plotting checked in MATLAB |
| Activation timing | Physical LAT in `pulse_ep.lat_ms`; EnSite DxL reference ticks, sampling frequency and WOI are mapped when present |
| Conduction velocity | `pe_openep_conduction_velocity` prepares physical LAT for OpenEP's RBF calculation; use genuine LAT and nondegenerate point positions |
| Contact-force courses | Shared REST/file selection; CARTO per-point files and uniquely matched EnSite time windows |
| Electrograms and ECG | Optional point-linked CARTO and EnSite DxL signal arrays, including both unipoles and available reference/ECG channels |
| Ablation tags | Explicit study/marker selection produces `rfindex`; PFA and non-RF markers are excluded |

Extended native checks covered two clinical CARTO maps (126 signal-bearing
points, including 25 with contact force), an EnSite X electrical map with
3,306 points, and a point-only EnSite DxL map with 100 recordings at 2 kHz.
REST and CLI/MAT signal arrays agreed. OpenEP's NLEO and electrogram-duration
functions ran on three CARTO recordings. The CV helper reproduced a synthetic
0.5 m/s control within 2 × 10⁻¹⁵ m/s and produced a map from selected clinical
EnSite LAT points. A three-tag synthetic RF control agreed with an independent
triangle-area calculation. These are interoperability checks; they do not
establish clinical accuracy of the analysis algorithms.

The examined upstream revision contains an experimental
[`import_ensitex.m`](https://github.com/openep/openep-core/blob/c80852140349cec77ff7964bcf7945aaf0b737d7/import_ensitex.m)
that loads a developer-specific local data file. The bridge's benefit is a
tested route from the pulse-ep database; it does not imply that no EnSite X
importer exists upstream.

## File export

For a bulk export on the machine that holds the database there is also

```bash
pulse-ep-export-openep --map-id 12 -o map12.mat
```

Load the file and reconstruct the triangulation:

```matlab
load('map12.mat', 'userdata');
tr = userdata.surface.triRep;
userdata.surface.triRep = triangulation(tr.Triangulation, tr.X);
area_cm2 = getArea(userdata);
```

REST and file export share the Python mapping. MATLAB point names and tags
are cell arrays, and numeric per-point/per-vertex vectors are columns.
REST and CLI use the same waveform and ablation selection. Contact-force
windows are included when available. Add `--include-signals` for electrograms
and ECG, and `--ablation-scope study` or `--ablation-ids 17,18,19` to select RF
markers explicitly. Signals can substantially increase export size.

## What maps across

| pulse-ep | `userdata` |
| --- | --- |
| `vertices`, `triangles` | `surface.triRep.X`, `.Triangulation` (1-based) |
| `is_vertex_at_edge` | `surface.isVertexAtRim` |
| stored surface normals | `surface.normals` |
| study vendor | `systemName` (`carto` or `ensitex`) |
| `activation_time` (or negative `pacemap_score`), `voltage_bipolar` | `surface.act_bip` (columns 1, 2) |
| `voltage_unipolar`, `impedance`, `contact_force` | `surface.uni_imp_frc` (columns 1–3) |
| `MeasurementPoint.position` | `electric.egmX` |
| `.source_id`, `.tags` | `electric.names`, `.tags` |
| point voltage measurements | `electric.voltages.bipolar` / `.unipolar` |
| every named surface scalar | `surface.signalMaps` |
| every named point measurement | `electric.signalProps` |
| `.annotations` | `electric.annotations.referenceAnnot` / `.mapAnnot` / `.woi` |
| `.electrodes` | `electric.electrodeNames_bip` |
| computed | `electric.egmSurfX`, `.barDirection` |

## Additional measurements

The five positional surface columns are supplemented by OpenEP's extensible
containers. Each `surface.signalMaps{i}` contains `name`, `map` and
`propSettings`, plus pulse-ep metadata `kind`, `unit`, `source` and
`statusMask`. All vertex-aligned fields are retained, including multiple
fields of the same kind and the original positive pace scores. Missing
values remain NaN. Acquisition settings are left empty when unavailable.

Each `electric.signalProps{i}` carries a point-aligned `name` array and
numeric `value` vector, with `fieldName`, `kind` and `unit` identifying the
quantity. A missing measurement is NaN. Measurements sharing a name but
having different kinds or units remain separate properties.

For example, inspect a stored point quantity before analysing it:

```matlab
props = userdata.electric.signalProps;
keys = cellfun(@(p) p.fieldName, props, 'UniformOutput', false);
idx = find(strcmp(keys, 'cfe_mean')); % empty if this map has no CFE measurements
for i = idx(:)'
    fprintf('%s [%s]: %d finite values\n', props{i}.fieldName, ...
            props{i}.unit, sum(isfinite(props{i}.value)));
end
```

OpenEP's `getSurfaceData` still addresses its fixed standard columns. For
another field, select its record and supply the values to `drawMap`:

```matlab
names = cellfun(@(f) f.name, userdata.surface.signalMaps, 'UniformOutput', false);
disp(names); % inspect the fields actually present on this map
field = userdata.surface.signalMaps{1}; % choose the required entry
values = field.map;
if ~isempty(field.statusMask)
    values(~field.statusMask) = NaN;
end
drawMap(userdata, 'type', 'act', 'data', values);
cb = findall(gcf, 'Type', 'ColorBar');
cb.Label.String = [field.name ' (' field.unit ')'];
```

This example uses OpenEP's custom-data plotting option; the field keeps its
own quantity and unit. It requires a nonempty surface field and measurement
points for OpenEP's display mask. `signalMaps` retains raw stored values and
exports the validity mask separately so analysis code can apply it explicitly.

## Pace-mapping compatibility

Pace maps follow CARTO's negative-score convention in OpenEP:

- `surface.act_bip(:,1) = -abs(pacemap_score)`: a score of 90% becomes -90.
- At measurement points, `mapAnnot - referenceAnnot` carries the same
  negative score. Missing scores, including unscored reference beats, remain
  NaN. When no reference offset was stored, the exporter uses zero solely
  as an encoding origin and records this in the notes.
- A real `activation_time` field takes precedence when a surface carries
  both quantities. Explicit activation-time measurements likewise take
  precedence at individual points.

`userdata.pulse_ep.surface_activation_kind`, `.surface_activation_encoding`
and `.surface_activation_unit` identify the surface representation.
`.point_activation_kinds` records the kind for each point. The native
pulse-ep data retain their declared quantities and original annotations.

For a pace map, OpenEP can display the negative score using its activation
plot. Relabel the colour bar because OpenEP otherwise calls this field LAT:

```matlab
drawMap(userdata, 'type', 'act');
cb = findall(gcf, 'Type', 'ColorBar');
cb.Label.String = 'Pace-match score (negative %)';
negative_point_scores = getActivationTime(userdata, 'units', 'samples');
```

Here OpenEP's `samples` option returns the unscaled annotation difference;
these values are percentages, not samples or milliseconds. Time-based
functions such as conduction velocity therefore do not have their usual
physiological meaning on a pace map. OpenEP's `generateInterpData(...,
'lat-map')` also clips negative interpolated values to zero; use the exported
surface score for its native pace-map display instead.

## Read the notes

`userdata.notes` records missing quantities, negative-score encoding and any
reconstructed reference origins. The CLI export prints the same notes.
The five standard surface columns leave absent quantities as NaN.
Additional quantities such as `cfe_mean` and `fractionation` are retained
in the named containers. Malformed surface fields whose length differs
from the vertex count are omitted with a note.

Standard OpenEP columns use milliseconds, millivolts, ohms, grams and percent.
Compatible declared units are converted (for example seconds to milliseconds
and volts to millivolts); unsupported units leave the standard values NaN and
are reported in the notes. Named containers retain the original values and
units. Standard surface columns apply the stored validity mask; `signalMaps`
keeps that mask separately alongside the unmodified values.

## Electrograms, reference signals and ECG

Import the vendor's waveform files with waveform storage enabled, then request:

```matlab
userdata = pe_to_openep(baseURL, token, mapId, true, ...
                       'IncludeSignals', true, 'ECGChannels', {'V1', 'V2'});
[traces, annotations, names] = getEgmsAtPoints(userdata, ...
    'iegm', 1, 'egmtype', 'bip-uni', 'reference', 'off');
```

`electric.egm`, `egmUni(:,:,1:2)`, `egmRef`, `egmRef2` and `ecg` follow the
measurement-point order. `sampleFrequency` records the sampling rate.
`electrodeNames_bip`, `electrodeNames_uni`, `egmUniX` and `ecgNames` identify
available channels and electrode locations. Unknown electrode positions stay
NaN. `pulse_ep.signals.sample_counts` records each unpadded window length;
shorter/missing recordings are padded with NaN. Mixed sampling rates require
separate exports; the bridge does not resample implicitly.

CARTO's point XML identifies mapping/reference channels within shared windows.
EnSite DxL `Wave_rov`, `Wave_uni_distal` and `Wave_uni_proximal` rows identify
points; `Wave_refs` and `Wave_refs2` identify freeze groups. These row-wise
files are imported separately from continuous `t_dws` tables. A DxL export
without a mesh becomes a point-only map, suitable for signal analysis.

Signal amplitudes retain their declared units in `pulse_ep.signals.units`.
Known V/µV units are converted to mV. EnSite exports that declare no amplitude
unit remain `unknown`; their values must not be interpreted with mV-based
thresholds. If calibration is independently known, supply
`'SignalScaleToMV', factor` (REST `signal_scale_to_mv`, CLI
`--signal-scale-to-mv`). This affects channels without a known voltage unit;
the explicit factor is recorded in the export.

The examined OpenEP `getEgmsAtPoints` divides the reference trace by 20 for
display and has an indexing issue when selecting a subset of reference
annotations. For quantitative reference-signal work, read `electric.egmRef`
and `electric.annotations.referenceAnnot` directly. The bridge preserves
the stored reference amplitude. See `openep_signal_demo.m` for a complete
REST-to-signal example.

## Conduction velocity

```matlab
[speed_m_per_s, pointIndices] = pe_openep_conduction_velocity(userdata);
```

This helper invokes OpenEP's unmodified `getConductionVelocity` on a copy
prepared with physical LAT in milliseconds and a common reference origin.
Calling that upstream function directly on sample indices can mix reference
offsets or sampling rates into the gradient. Pace scores and missing LAT are
excluded. Duplicate or degenerate positions cause an explicit error; select
a suitable set with `'Indices', pointIndices`. OpenEP's dense RBF calculation
can be expensive for large point sets. This is an interpolation-based
estimate, not a physiological validation of a dataset or pacing protocol.

## Contact force and ablation

Contact-force values and padded `nPoints × nSamples × 2` courses are supplied
to both export routes. CARTO files are linked by point ID; their instantaneous
force and vendor-relative millisecond axis are retained. EnSite courses use
milliseconds relative to the point's reference time. Uncovered or ambiguous
points stay NaN; no nearest recording outside the available interval is used.

RF markers require an explicit association, because they belong to a study:

```matlab
userdata = pe_to_openep(baseURL, token, mapId, true, 'AblationScope', 'study');
% Alternatively: 'AblationIds', [17 18 19] selects placed-point database IDs.
plotVisitags(userdata);
area_cm2 = pe_openep_ablation_area(userdata, 'Radius', 5);
```

Only use this after selecting markers in the appropriate coordinate frame
and anatomical region. OpenEP projects tags to the closest surface vertex
and counts whole triangles with centroids inside the specified radius; the
result is a geometric coverage estimate, not a measured lesion boundary.

`pe_openep_ablation_area` calls OpenEP's `getAblationArea` and handles its
small-selection edge cases. For one or two tags it repeats positions only in
a working copy, leaving the union of covered triangles unchanged. No tags or
no covered triangles return zero area, a false triangle mask and an empty
covered surface. The original markers and their count remain unchanged.

`rfindex.tag` contains RF positions and available duration, force, maximum
temperature/power, impedance and index values. Missing attributes stay NaN;
original attributes and distinct index families remain in `pulse_ep.ablation`.
Tag `time` follows OpenEP's importer convention of duration in seconds.
PFA sites and generic markers are not relabelled as RF. Manual RF time-series
data (`rf.originaldata`) and VisiTag grid histories are not synthesized from
summary tags. These require their own source recordings and remain absent.

## Licence

The format knowledge here comes from reading
[`importcarto_mem.m`](https://github.com/openep/openep-core) in openep-core,
which is Apache-2.0. No code is taken from it, and none from
[openep-py](https://github.com/openep/openep-py), which is GPL-3.0 and so
cannot be reused in an MIT package — the same line drawn for `carto-reader`.

If you use OpenEP, cite it:
[Williams *et al.*, Front. Physiol. 2021](https://www.frontiersin.org/articles/10.3389/fphys.2021.646023/full).
