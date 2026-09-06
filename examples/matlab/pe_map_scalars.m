function s = pe_map_scalars(baseURL, token, mapId)
%PE_MAP_SCALARS  Quantities a map carries: name, kind and unit, plus primary.
%
%   Clients should read the choice from here rather than assuming a field
%   name: a CARTO map is usually about activation_time, an EnSiteX one
%   about voltage_bipolar.
    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 30);
    s = webread(strcat(baseURL, "/epmaps/", string(mapId), "/scalars"), opts);
end
