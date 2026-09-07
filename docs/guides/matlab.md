# MATLAB toolbox

The toolbox packages the existing `pe_*` functions, their examples and an
optional `pulseep.Client` session object. Both interfaces use the same REST
functions and OpenEP conversion. The client remembers the server and bearer
token; it does not duplicate the analysis or import code.

## Install

Open the `pulse_ep_matlab-VERSION.mltbx` file in MATLAB and install it, or run:

```matlab
matlab.addons.toolbox.installToolbox('pulse_ep_matlab-VERSION.mltbx');
```

MATLAB manages the installed files and search path. Alternatively, add
`examples/matlab` from a source checkout to the path. The REST client uses
base MATLAB; OpenEP and any toolboxes needed by its analyses are separate.
The client targets R2020a and newer; the installation and integration checks
were executed on R2026a. This is not a claim of testing every supported release.

## A session client

```matlab
pe = pulseep.Client(getenv('PULSE_EP_BASE_URL'));
pe.login(getenv('PULSE_EP_USERNAME'), getenv('PULSE_EP_PASSWORD'));

studies = pe.studies();                  % table, including id/name/vendor
maps = pe.maps(studies.id(1));           % table, including point counts
mapId = maps.id(1);                     % choose the desired entry
fields = pe.scalars(mapId);             % field names, kinds, units and ranges
map = pe.loadMap(mapId, 'Include', {'mesh','fields','points'});

if ~isempty(map.faces)
    trisurf(map.faces, map.vertices(:,1), map.vertices(:,2), map.vertices(:,3));
    axis equal;
end
```

Check that the returned tables are nonempty before selecting a row. Study and
map IDs are database identifiers; they are not MATLAB row indices.
`toolbox_demo.m` provides an executable example with these checks.

Passwords are passed to the login request and are not retained by the client.
The token is private and transient; saving/reloading the client requires a
new login. `pe.useToken(token)` accepts an existing bearer token.
`pe.logout()` clears local credentials; it does not revoke previously issued
tokens on the server. `pe.isLoggedIn()` reports whether local credentials are
present, not whether the server still accepts them. An authentication rejection
clears them and asks for a new login. Use HTTPS for remote connections.

## Choose the data to transfer

`loadMap` uses the stored, raw representation. Without an `Include` argument
it requests all components below. An explicit empty selection requests only
map/study metadata. Component selection is applied on the server; omitted
components are absent from the response. It requires a server supporting the
raw `include` parameter; a server that ignores the selection produces an
explicit compatibility error.

| Component | Contents |
| --- | --- |
| `mesh` | Vertices, triangles, normals, triangle areas and rim flags |
| `fields` | All stored named surface fields, units, validity and provenance; available legacy surface arrays |
| `points` | Full point measurements with kinds/units, electrodes, tags, annotations and legacy point data |
| `markers` | Study-level placed markers; anatomical association must be selected for analysis |
| `waveforms` | Stored signal metadata and download links, without the sample payloads |

```matlab
metadata = pe.loadMap(mapId, 'Include', {});
geometry = pe.loadMap(mapId, 'Include', {'mesh'});
analysis = pe.loadMap(mapId, 'Include', {'mesh','fields','points'});
allData = pe.loadMap(mapId);
```

`map.vertices`, `map.faces` and `map.points` provide convenient numeric arrays;
omitted or absent geometry becomes an empty array. Faces in `map.faces` are
1-based. `map.data` retains the complete decoded response and its metadata;
faces there remain 0-based as specified by `map.data.index_base`.
`map.data.selection.included` distinguishes a component not requested from
one requested but empty. Raw fields retain their validity masks separately;
they are not display-processed or interpolated by this client.

`'ScalarName','voltage_bipolar'` selects the convenient `map.scalars` vector
when `fields` is included. It does not limit the named fields transferred.

## Points, signals and OpenEP

```matlab
page = pe.points(mapId, 'Limit', 100, 'Offset', 0);
signals = pe.waveforms(mapId);
% Choose a waveform ID from signals.waveforms before downloading:
% path = pe.downloadWaveform(waveformId, 'recording.parquet');
% samples = parquetread(path);

userdata = pe.openep(mapId, 'IncludeSignals', true, 'ECGChannels', {'V1','V2'});
```

Point pages contain the API's flattened measurements, units and annotations;
use `loadMap(...,'Include',{'points'})` for full electrode and quantity metadata.
Offsets and `point_index` values in API responses are 0-based. `Limit=0`
requests all points. Signal lists may include unassigned study recordings;
the OpenEP exporter checks recorded map/point identities before association.

OpenEP options include `IncludePoints`, `IncludeSignals`, `ECGChannels`,
`SignalScaleToMV`, `AblationScope` and `AblationIds`. See the
[OpenEP guide](openep.md) for units, missing data, RF association and the
separately installed analysis functions. Waveform channels can be selected
for OpenEP ECG export; Parquet download retrieves the selected stored window
in full. The toolbox does not claim arbitrary server-side slicing of signals.

`pe.areas(mapId, intervals, 'ScalarName', name, 'Distance', 5)` calls the shared
server interval-area calculation; it does not implement another integrator.

## Direct functions remain supported

```matlab
url = getenv('PULSE_EP_BASE_URL');
token = pe_login(url, getenv('PULSE_EP_USERNAME'), getenv('PULSE_EP_PASSWORD'));
studies = pe_list_studies(url, token);       % struct array
maps = pe_list_maps(url, token, studies(1).id);
map = pe_load_map(url, token, maps(1).id, 'Include', {'mesh','fields'});
```

Existing calls to `pe_get_mesh` keep their display default and signatures.
`pe_load_map` provides the raw/selective entry point. The toolbox does not
require adopting the session object.

## Build and verify a release

From the source archive, using MATLAB R2023a or newer to package:

```matlab
addpath('examples/matlab');
filename = build_toolbox();
```

The version is read from `pyproject.toml`. The builder stages only MATLAB
source, the MIT licence and the two client guides. Generated figures, local
settings, clinical data and the Python environment are not included.
The output is `dist/pulse_ep_matlab-VERSION.mltbx`; attach it to the matching
release after verification. The toolbox has a stable identity for updates.

`tests/matlab/test_client.m` checks the installed client against a disposable
test server containing synthetic controls. Its required environment and
fixture setup are documented alongside the tests. Test from outside the source
tree so an installed toolbox cannot accidentally resolve source-checkout code.
