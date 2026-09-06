function areas = pe_areas_per_interval(baseURL, token, mapId, intervals, ...
                                       scalarName, distance)
%PE_AREAS_PER_INTERVAL  Call /calculate_areas_for_intervals.
%
%   intervals : N-by-2 numeric matrix of [lo hi] bins (e.g. [50 60; 60 70; ...]).
%   areas     : Nx1 double, surface area in cm^2 per interval (NaN for empty).
    if nargin < 5; scalarName = ""; end   % "" -> the map's primary quantity
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
