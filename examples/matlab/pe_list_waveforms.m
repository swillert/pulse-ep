function page = pe_list_waveforms(baseURL, token, mapId)
%PE_LIST_WAVEFORMS List map-associated and unassigned study signal windows.
%   No samples are transferred. Rows can reference the same stored window
%   for several points. An unassigned study window is not necessarily linked
%   to this map; OpenEP export applies recorded point/map associations.
    opts = weboptions('HeaderFields', {'Authorization', char(strcat("Bearer ",token))}, ...
                      'ContentType','json','Timeout',60);
    page = webread(strcat(baseURL,"/epmaps/",string(mapId),"/waveforms"),opts);
end
