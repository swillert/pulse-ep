classdef Client < handle
%CLIENT A session convenience layer over the pulse-ep MATLAB functions.
%   PE = pulseep.Client(URL); PE.login(USERNAME,PASSWORD);
%   STUDIES = PE.studies(); MAPS = PE.maps(STUDIES.id(1));
%   MAP = PE.loadMap(MAPS.id(1),'Include',{'mesh','fields','points'});
%   USERDATA = PE.openep(MAPS.id(1),'IncludeSignals',true);
%   Direct pe_* functions remain available. Passwords are not retained and
%   the token is transient: saved/reloaded client objects require login again.
    properties (SetAccess = private)
        BaseURL
    end
    properties (Access = private, Transient)
        Token = ""
    end
    methods
        function obj = Client(baseURL)
            if nargin == 0; baseURL = getenv('PULSE_EP_BASE_URL'); end
            if ~(ischar(baseURL) && isrow(baseURL) || isstring(baseURL) && isscalar(baseURL))
                error('pulse_ep:InvalidURL','Supply one http:// or https:// server URL.');
            end
            url = regexprep(char(baseURL), '/+$', '');
            if isempty(regexp(url, '^https?://[^/\s?#@]+(/[^\s?#]*)?$', 'once'))
                error('pulse_ep:InvalidURL','Supply an HTTP(S) URL without credentials, query or fragment.');
            end
            obj.BaseURL = string(url);
        end
        function login(obj, username, password)
            obj.logout();
            obj.Token = string(pe_login(obj.BaseURL, username, password));
        end
        function useToken(obj, token)
            if ~(ischar(token) && isrow(token) || isstring(token) && isscalar(token)) || ...
                    strlength(string(token)) == 0 || contains(string(token), newline)
                error('pulse_ep:InvalidToken','Supply one nonempty bearer token.');
            end
            obj.Token = string(token);
        end
        function logout(obj)
            obj.Token = "";
        end
        function tf = isLoggedIn(obj)
            % Reports local credentials, not a live server check of expiry.
            tf = strlength(obj.Token) > 0;
        end
        function t = studies(obj)
            rows = obj.call(@pe_list_studies);
            t = local_table(rows, {'id','study_name','vendor'}, {'id'});
        end
        function t = maps(obj, studyId)
            local_id(studyId);
            rows = obj.call(@pe_list_maps, studyId);
            t = local_table(rows, {'id','study_id','map_name','number_of_points','measurement_points'}, ...
                            {'id','study_id','number_of_points','measurement_points'});
        end
        function data = scalars(obj, mapId)
            local_id(mapId); data = obj.call(@pe_map_scalars, mapId);
        end
        function data = points(obj, mapId, varargin)
            local_id(mapId); data = obj.call(@pe_list_points, mapId, varargin{:});
        end
        function data = waveforms(obj, mapId)
            local_id(mapId); data = obj.call(@pe_list_waveforms, mapId);
        end
        function data = loadMap(obj, mapId, varargin)
            local_id(mapId); data = obj.call(@pe_load_map, mapId, varargin{:});
        end
        function data = openep(obj, mapId, varargin)
            local_id(mapId);
            p = inputParser;
            p.KeepUnmatched = true;
            addParameter(p, 'IncludePoints', true, @(x) islogical(x) && isscalar(x));
            parse(p, varargin{:});
            names = fieldnames(p.Unmatched);
            options = cell(1, 2*numel(names));
            for i = 1:numel(names)
                options{2*i-1} = names{i}; options{2*i} = p.Unmatched.(names{i});
            end
            data = obj.call(@pe_to_openep, mapId, p.Results.IncludePoints, options{:});
        end
        function filename = downloadWaveform(obj, waveformId, filename)
            local_id(waveformId);
            filename = obj.call(@pe_download_waveform, waveformId, filename);
        end
        function values = areas(obj, mapId, intervals, varargin)
            local_id(mapId);
            p = inputParser; addParameter(p,'ScalarName',''); addParameter(p,'Distance',5);
            parse(p,varargin{:});
            values = obj.call(@pe_areas_per_interval, mapId, intervals, ...
                              p.Results.ScalarName,p.Results.Distance);
        end
    end
    methods (Access = private)
        function result = call(obj, f, varargin)
            if ~obj.isLoggedIn()
                error('pulse_ep:NotLoggedIn','Call login(username,password) or useToken(token) first.');
            end
            try
                result = f(obj.BaseURL, obj.Token, varargin{:});
            catch e
                if contains(e.identifier,'HTTP401') || contains(e.identifier,'HTTP422')
                    obj.logout();
                    error('pulse_ep:AuthenticationRequired', ...
                          'The server rejected the credentials. Log in again.');
                end
                rethrow(e);
            end
        end
    end
end

function local_id(value)
    validateattributes(value, {'numeric'}, {'scalar','integer','positive','finite'});
end

function t = local_table(rows, names, numericNames)
% Stable columns also for empty results and null vendor/count values.
    n = numel(rows); t = table();
    for j = 1:numel(names)
        name = names{j}; numeric = ismember(name,numericNames);
        if numeric; column = nan(n,1); else; column = strings(n,1); end
        for i = 1:n
            if iscell(rows); row = rows{i}; else; row = rows(i); end
            if ~isfield(row,name) || isempty(row.(name)); continue; end
            if numeric; column(i) = double(row.(name)); else; column(i) = string(row.(name)); end
        end
        t.(name) = column;
    end
end
