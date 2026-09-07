function map = pe_load_map(baseURL, token, mapId, varargin)
%PE_LOAD_MAP Load stored analysis data with a server-side component selection.
%   MAP = PE_LOAD_MAP(URL, TOKEN, ID) returns all stored analysis components.
%   ...,'Include',{'mesh','fields'} omits points, markers and waveform lists.
%   ...,'Include',{} returns map/study metadata only.
%   Components: mesh, fields, points, markers, waveforms. Waveforms are
%   metadata/download links; samples are fetched by pe_download_waveform.
%   MAP.data preserves the full response (0-based faces, units, provenance).
%   MAP.vertices and MAP.faces are ready for MATLAB (1-based faces).
%   ...,'ScalarName','voltage_bipolar' chooses MAP.scalars. All named fields
%   remain in MAP.data.mesh_data.scalar_fields when 'fields' is included.
    p = inputParser;
    addParameter(p, 'Include', {'mesh','fields','points','markers','waveforms'});
    addParameter(p, 'ScalarName', '');
    parse(p, varargin{:});
    validateattributes(mapId, {'numeric'}, {'scalar','integer','positive','finite'});
    map = pe_get_mesh(baseURL, token, mapId, p.Results.ScalarName, 5, 'raw', ...
                      'Include', p.Results.Include);
end
