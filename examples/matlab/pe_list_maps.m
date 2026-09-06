function maps = pe_list_maps(baseURL, token, studyId)
%PE_LIST_MAPS  List EP maps in a study.
    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 30);
    maps = webread( ...
        sprintf("%s/list_epmaps_in_study/%d", baseURL, studyId), opts);
end

% -----------------------------------------------------------------------
