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
%     PE_SCALAR_NAME  default "act"
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
if isempty(scalarName); scalarName = 'act'; end
distMM = str2double(getenv('PE_DISTANCE_MM'));
if isnan(distMM); distMM = 5.0; end
fprintf('map_id=%d  scalar=%s  distance=%.1f mm\n', mapId, scalarName, distMM);

% --- 2. Define score bins ----------------------------------------------
% Default clinical bins for pace-mapping similarity; override below for
% your own colormap intervals.
breaks = [50 60 70 80 90 100];
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
fprintf('\nTotal covered area = %.3f cm^2\n', sum(areas, 'omitnan'));

% --- 4. Bar plot --------------------------------------------------------
figure('Name', sprintf('pulse-ep map %d — areas per interval', mapId), 'Color', 'w');
bar(areas, 'FaceColor', '#3a76ff');
set(gca, 'XTickLabel', labels);
xlabel('Score interval [%]');
ylabel('Area [cm^2]');
title(sprintf('Map %d — area per %s score interval (d = %.1f mm)', ...
              mapId, scalarName, distMM));
grid on;
exportgraphics(gcf, 'areas_per_interval.png', 'Resolution', 150);
fprintf('Wrote areas_per_interval.png\n');
