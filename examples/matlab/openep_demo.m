% OPENEP_DEMO  Turn a stored map into an OpenEP `userdata` structure.
%
%   1. Logs in and picks a map (override with PE_MAP_ID).
%   2. Fetches it as `userdata` over REST — no database credential, no file.
%   3. Prints what the structure holds, and the notes on what it could not.
%   4. Computes the surface area from the triangulation, which is a check
%      that the geometry survived JSON and the 0-based to 1-based boundary:
%      it must agree with GET /calculate_areas_for_intervals over the full
%      range of the map's own quantity.
%
%   The point of doing this at all: OpenEP parses CARTO and Precision itself
%   but not EnSite X, and pulse-ep does. A map from either vendor becomes one
%   structure, so any OpenEP analysis runs on both.
%
%   With OpenEP on the path you can carry on from here directly:
%       drawMap(userdata);
%       getMeanVoltage(userdata);
%
%   Run with:
%     openep_demo
%
%   Environment variables (see ../README.md):
%     PULSE_EP_BASE_URL   default http://127.0.0.1:5000
%     PULSE_EP_USERNAME   default admin
%     PULSE_EP_PASSWORD   required
%     PE_MAP_ID           optional; otherwise the first map of the first study

baseURL  = getenv('PULSE_EP_BASE_URL');
if isempty(baseURL); baseURL = 'http://127.0.0.1:5000'; end
username = getenv('PULSE_EP_USERNAME');
if isempty(username); username = 'admin'; end
password = getenv('PULSE_EP_PASSWORD');
if isempty(password)
    error('PULSE_EP_PASSWORD is not set. See examples/README.md.');
end

% --- 1. Login & pick a map ---------------------------------------------
token = pe_login(baseURL, username, password);

mapIdEnv = getenv('PE_MAP_ID');
if ~isempty(mapIdEnv)
    mapId = str2double(mapIdEnv);
else
    studies = pe_list_studies(baseURL, token);
    if isempty(studies); error('No studies in the database.'); end
    maps = pe_list_maps(baseURL, token, studies(1).id);
    if isempty(maps); error('Study has no EP maps.'); end
    mapId = maps(1).id;
end
fprintf('Map id %d\n', mapId);

% --- 2. Fetch it as userdata -------------------------------------------
% pe_to_openep prints userdata.notes itself. Read them: they say which slots
% are empty, which quantities OpenEP has no room for, and — the one that
% matters — whether a pace-mapping score was left out of the activation-time
% column on purpose.
userdata = pe_to_openep(baseURL, token, mapId);

% --- 3. What came across ------------------------------------------------
tr = userdata.surface.triRep;
fprintf('\nsurface\n');
fprintf('  triRep            %d vertices, %d triangles\n', ...
        size(tr.Points, 1), size(tr.ConnectivityList, 1));
fprintf('  act_bip           activation %s, bipolar %s\n', ...
        local_filled(userdata.surface.act_bip(:,1)), ...
        local_filled(userdata.surface.act_bip(:,2)));
fprintf('  uni_imp_frc       unipolar %s, impedance %s, force %s\n', ...
        local_filled(userdata.surface.uni_imp_frc(:,1)), ...
        local_filled(userdata.surface.uni_imp_frc(:,2)), ...
        local_filled(userdata.surface.uni_imp_frc(:,3)));
fprintf('electric\n');
fprintf('  %d points, %d with a bipolar voltage\n', ...
        size(userdata.electric.egmX, 1), ...
        sum(~isnan(userdata.electric.voltages.bipolar)));
fprintf('  contact force     %s\n', local_filled(userdata.electric.force.force));

% --- 4. The geometry check ---------------------------------------------
% Area straight off the triangulation. If the 1-based conversion or the JSON
% round trip had gone wrong, this would not match what the server computes.
P  = tr.Points;
T  = tr.ConnectivityList;
v1 = P(T(:,2),:) - P(T(:,1),:);
v2 = P(T(:,3),:) - P(T(:,1),:);
areaFromTriRep = sum(0.5 * vecnorm(cross(v1, v2, 2), 2, 2)) / 100;   % mm^2 -> cm^2
fprintf('\nsurface area from triRep: %.2f cm2\n', areaFromTriRep);

fprintf(['\nOpenEP takes it from here — drawMap(userdata), ' ...
         'getMeanVoltage(userdata), and the rest.\n']);

function s = local_filled(column)
%LOCAL_FILLED  Whether a slot carries values or is an empty one.
%   An empty OpenEP slot is NaN throughout: a quantity this map never
%   measured. Saying so beats printing a range of NaNs.
    n = sum(~isnan(column));
    if n == 0
        s = 'empty';
    else
        s = sprintf('%d values (%.3f … %.3f)', n, min(column), max(column));
    end
end
