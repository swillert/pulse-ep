function page = pe_list_points(baseURL, token, mapId, varargin)
%PE_LIST_POINTS Read a point page with measurements, units and annotations.
%   ...,'Limit',500,'Offset',0 controls paging. Limit 0 requests all points.
%   Offset and returned point_index values follow the API's zero-based convention.
%   For full electrode geometry and per-measurement kind/unit metadata use
%   pe_load_map(...,'Include',{'points'}).
    p = inputParser;
    valid = @(x) isnumeric(x) && isscalar(x) && isfinite(x) && x >= 0 && fix(x) == x;
    addParameter(p, 'Limit', 500, valid);
    addParameter(p, 'Offset', 0, valid);
    parse(p, varargin{:});
    opts = weboptions('HeaderFields', {'Authorization', char(strcat("Bearer ",token))}, ...
                      'ContentType','json','Timeout',60);
    page = webread(strcat(baseURL,"/epmaps/",string(mapId),"/points"),opts, ...
                   'limit',p.Results.Limit,'offset',p.Results.Offset);
end
