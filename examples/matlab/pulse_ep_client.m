% PULSE_EP_CLIENT  Minimal REST client for pulse-ep (R2020a+).
%
%   This file defines four utility functions that talk to a running
%   pulse-ep server over its JSON REST API. They use only built-in
%   MATLAB facilities (webread / webwrite) — no Toolbox required.
%
%   token   = pe_login(baseURL, username, password)
%   studies = pe_list_studies(baseURL, token)
%   maps    = pe_list_maps(baseURL, token, studyId)
%   mesh    = pe_get_mesh(baseURL, token, mapId, scalarName, distance)
%   areas   = pe_areas_per_interval(baseURL, token, mapId, intervals, scalarName, distance)
%
%   See pulse_ep_demo.m and areas_per_interval.m for runnable examples.

function pulse_ep_client  %#ok<*STOUT>
    error('pulse_ep_client.m only defines helper functions; call them directly.');
end

% -----------------------------------------------------------------------
function token = pe_login(baseURL, username, password)
%PE_LOGIN  Exchange username/password for a JWT bearer token.
    body = jsonencode(struct('username', username, 'password', password));
    opts = weboptions( ...
        'MediaType',     'application/json', ...
        'ContentType',   'json', ...
        'RequestMethod', 'POST', ...
        'Timeout',       30);
    resp  = webwrite(strcat(baseURL, "/login_user"), body, opts);
    token = resp.access_token;
end

% -----------------------------------------------------------------------
function studies = pe_list_studies(baseURL, token)
%PE_LIST_STUDIES  Return a struct array with fields id, study_name.
    opts    = weboptions('HeaderFields', ...
              {'Authorization', char(strcat("Bearer ", token))}, ...
              'ContentType', 'json', 'Timeout', 30);
    studies = webread(strcat(baseURL, "/list_studies"), opts);
end

% -----------------------------------------------------------------------
function maps = pe_list_maps(baseURL, token, studyId)
%PE_LIST_MAPS  List EP maps in a study.
    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 30);
    maps = webread( ...
        sprintf("%s/list_epmaps_in_study/%d", baseURL, studyId), opts);
end

% -----------------------------------------------------------------------
function mesh = pe_get_mesh(baseURL, token, mapId, scalarName, distance)
%PE_GET_MESH  Fetch one map's mesh and per-vertex scalars.
%
%   Returns a struct with fields:
%     mesh.vertices       [Nv x 3] double
%     mesh.faces          [Nt x 3] int32     (1-based for MATLAB)
%     mesh.scalars        [Nv x 1] double    (NaN outside `distance`)
%     mesh.normalized     [Nv x 1] double
%     mesh.points         [Np x 3] double    catheter coordinates
%     mesh.point_scalars  [Np x 1] double
    if nargin < 4 || isempty(scalarName); scalarName = "act";    end
    if nargin < 5 || isempty(distance);   distance   = 5.0;       end

    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 60);
    data = webread( ...
        strcat(baseURL, "/get_mesh_data"), opts, ...
        'map_id', mapId, 'scalar_name', scalarName, 'distance', distance);

    md = data.mesh_data;
    pd = data.point_data;

    mesh.vertices   = local_to_matrix(md.vertices, 3);
    mesh.faces      = int32(local_to_matrix(md.faces, 3)) + 1;       % 0→1-indexed
    mesh.scalars    = local_to_column(md.scalar_data);
    mesh.normalized = local_to_column(md.normalized_scalar_data);

    if isfield(pd, 'coordinates') && ~isempty(pd.coordinates)
        mesh.points = local_to_matrix(pd.coordinates, 3);
    else
        mesh.points = zeros(0, 3);
    end
    if isfield(pd, 'scalar_data') && ~isempty(pd.scalar_data)
        mesh.point_scalars = local_to_column(pd.scalar_data);
    else
        mesh.point_scalars = zeros(0, 1);
    end
end

% -----------------------------------------------------------------------
function areas = pe_areas_per_interval(baseURL, token, mapId, intervals, ...
                                       scalarName, distance)
%PE_AREAS_PER_INTERVAL  Call /calculate_areas_for_intervals.
%
%   intervals : N-by-2 numeric matrix of [lo hi] bins (e.g. [50 60; 60 70; ...]).
%   areas     : Nx1 double, surface area in cm^2 per interval (NaN for empty).
    if nargin < 5 || isempty(scalarName); scalarName = "act"; end
    if nargin < 6 || isempty(distance);   distance   = 5.0;   end

    % MATLAB serialises [N x 2] as nested JSON arrays — exactly what the
    % Flask endpoint expects.
    payload = struct( ...
        'map_id',      mapId, ...
        'scalar_name', scalarName, ...
        'distance',    distance, ...
        'intervals',   intervals);
    body = jsonencode(payload);

    opts = weboptions( ...
        'HeaderFields', {'Authorization', char(strcat("Bearer ", token)); ...
                         'Content-Type',  'application/json'}, ...
        'MediaType',     'application/json', ...
        'ContentType',   'json', ...
        'RequestMethod', 'POST', ...
        'Timeout',       60);
    resp = webwrite(strcat(baseURL, "/calculate_areas_for_intervals"), body, opts);

    raw = resp.areas;
    if iscell(raw)
        areas = cellfun(@local_or_nan, raw);
        areas = areas(:);
    else
        areas = double(raw(:));
    end
end

% -----------------------------------------------------------------------
function M = local_to_matrix(cellOfRows, ncols)
%LOCAL_TO_MATRIX  Convert a cell-of-rows (from JSON) to a numeric matrix.
    if iscell(cellOfRows)
        rows = cellfun(@(r) reshape(double(r), 1, ncols), ...
                       cellOfRows, 'UniformOutput', false);
        M = vertcat(rows{:});
    else
        % If MATLAB already simplified it to a 2-D numeric array.
        M = double(cellOfRows);
    end
end

% -----------------------------------------------------------------------
function v = local_to_column(values)
%LOCAL_TO_COLUMN  Convert a cell or array of (numeric|null) to a column.
    if iscell(values)
        v = cellfun(@(x) local_or_nan(x), values);
        v = v(:);
    else
        v = double(values(:));
    end
end

function x = local_or_nan(v)
    if isempty(v); x = NaN; else; x = double(v); end
end
