function studies = pe_list_studies(baseURL, token)
%PE_LIST_STUDIES  Return a struct array with fields id, study_name.
    opts    = weboptions('HeaderFields', ...
              {'Authorization', char(strcat("Bearer ", token))}, ...
              'ContentType', 'json', 'Timeout', 30);
    studies = webread(strcat(baseURL, "/list_studies"), opts);
end

% -----------------------------------------------------------------------
