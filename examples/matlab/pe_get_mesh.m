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
    % Empty asks the server for the map's own primary quantity, which
    % differs between vendors. See GET /epmaps/<id>/scalars.
    if nargin < 4; scalarName = "";    end
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
