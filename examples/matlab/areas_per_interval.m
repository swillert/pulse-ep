% AREAS_PER_INTERVAL  Cross-language reproducibility demo in MATLAB.
%
%   Calls /calculate_areas_for_intervals on a pulse-ep server and
%   tabulates / bar-plots the surface area per score bin — the same
%   reduction the bundled web viewer and the clinical Excel reports
%   compute. Doing it in MATLAB from the raw REST payload proves the
%   platform is faithful across stacks.
%
%   Run:
%     pulse_ep_areas_per_interval
%
%   Optional env overrides:
%     PE_MAP_ID       integer, map to analyse (default: first map of first study)
%     PE_SCALAR_NAME  unset -> the map's own primary quantity
%     PE_DISTANCE_MM  default 5.0

baseURL  = getenv('PULSE_EP_BASE_URL');
if isempty(baseURL); baseURL = 'http://127.0.0.1:5000'; end
username = getenv('PULSE_EP_USERNAME');
if isempty(username); username = 'admin'; end
password = getenv('PULSE_EP_PASSWORD');
if isempty(password)
    error('PULSE_EP_PASSWORD is not set. See examples/README.md.');
end

% --- 1. Connection & target map ----------------------------------------
token   = pe_login(baseURL, username, password);
studies = pe_list_studies(baseURL, token);
if isempty(studies); error('No studies in the database.'); end

mapIdEnv = getenv('PE_MAP_ID');
if ~isempty(mapIdEnv)
    mapId = str2double(mapIdEnv);
else
    maps = pe_list_maps(baseURL, token, studies(1).id);
    if isempty(maps); error('First study has no EP maps.'); end
    mapId = maps(1).id;
end
scalarName = getenv('PE_SCALAR_NAME');
% left empty on purpose: the server resolves the map's primary quantity
distMM = str2double(getenv('PE_DISTANCE_MM'));
if isnan(distMM); distMM = 5.0; end
% The server names the quantities a map carries; use that rather than
% printing an empty string when none was requested.
meta = pe_map_scalars(baseURL, token, mapId);
if isempty(scalarName); quantity = meta.primary; else; quantity = scalarName; end
quantityUnit = '';
for k = 1:numel(meta.scalars)
    if strcmp(meta.scalars(k).name, quantity); quantityUnit = meta.scalars(k).unit; end
end
fprintf('map_id=%d  scalar=%s  distance=%.1f mm\n', mapId, quantity, distMM);

% --- 2. Define bins -----------------------------------------------------
% Default clinical bins for pace-mapping similarity (0-100 %). They do not
% fit every quantity: a bipolar voltage map is in mV and an activation map
% in ms, so these bins would report zero area everywhere. Override with
% e.g. PE_INTERVAL_BREAKS="0,0.5,1.5,3,15" for voltage.
breaksEnv = getenv('PE_INTERVAL_BREAKS');
if isempty(breaksEnv)
    breaks = [50 60 70 80 90 100];
else
    breaks = str2double(strsplit(breaksEnv, ','));
end
intervals = [breaks(1:end-1)' breaks(2:end)'];   % N-by-2
labels = arrayfun(@(lo, hi) sprintf('%g–%g', lo, hi), ...
                  intervals(:,1), intervals(:,2), 'UniformOutput', false);

% --- 3. Call the platform endpoint -------------------------------------
areas = pe_areas_per_interval(baseURL, token, mapId, intervals, scalarName, distMM);

T = table((1:numel(areas))', string(labels), areas, ...
          'VariableNames', {'bin', 'interval', 'area_cm2'});
disp(' ');
disp('Area per score interval (cm^2):');
disp(T);
totalArea = sum(areas, 'omitnan');
fprintf('\nTotal covered area = %.3f cm^2\n', totalArea);
if totalArea == 0
    warning(['Every interval is empty. The bins (' num2str(breaks) ...
             ') likely do not match this quantity''s range - set PE_INTERVAL_BREAKS.']);
end

% --- 4. Bar plot --------------------------------------------------------
figure('Name', sprintf('pulse-ep map %d — areas per interval', mapId), 'Color', 'w');
bar(areas, 'FaceColor', '#3a76ff');
set(gca, 'XTickLabel', labels);
if isempty(quantityUnit)
    xlabel(sprintf('%s interval', quantity));
else
    xlabel(sprintf('%s interval [%s]', quantity, quantityUnit));
end
ylabel('Area [cm^2]');
title(sprintf('Map %d — area per %s interval (d = %.1f mm)', ...
              mapId, quantity, distMM));
grid on;
exportgraphics(gcf, 'areas_per_interval.png', 'Resolution', 150);
fprintf('Wrote areas_per_interval.png\n');
