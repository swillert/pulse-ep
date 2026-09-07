function path = pe_download_waveform(baseURL, token, waveformId, path)
%PE_DOWNLOAD_WAVEFORM Download stored samples; read with parquetread(path).
    opts = weboptions('HeaderFields', ...
        {'Authorization', char(strcat("Bearer ", token))}, 'Timeout', 120);
    path = websave(path, strcat(baseURL, "/waveforms/", string(waveformId), "/download"), opts);
end
