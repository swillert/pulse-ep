% OPENEP_DEMO  Turn a stored map into an OpenEP `userdata` structure.
%
%   1. Logs in and picks a map (override with PE_MAP_ID).
%   2. Fetches it as `userdata` over REST — no database credential, no file.
%   3. Prints what the structure holds, and the notes on what it could not.
%   4. Computes the surface area independently from the triangulation.
%   5. If OpenEP is installed, runs its area and voltage analyses, checks the
%      results against the downloaded arrays, and draws the map with OpenEP.
%
%   A stored map from CARTO or EnSite X becomes one structure for OpenEP
%   analyses supported by the available quantities. All named surface fields
%   and point measurements remain accessible in signalMaps and signalProps.
%
%   With OpenEP on the path you can carry on from here directly:
%       drawMap(userdata, 'type', 'bip');
%       getMeanVoltage(userdata);
%
%   Run with:
%     run('/path/to/pulse-ep/examples/matlab/openep_demo.m')
%   Use the explicit path: OpenEP also ships a script called openep_demo.m.
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
% pe_to_openep prints userdata.notes itself, including missing quantities
% and negative-score encoding for pace maps.
userdata = pe_to_openep(baseURL, token, mapId);

% --- 3. What came across ------------------------------------------------
tr = userdata.surface.triRep;
fprintf('\nsurface\n');
fprintf('  triRep            %d vertices, %d triangles\n', ...
        size(tr.Points, 1), size(tr.ConnectivityList, 1));
fprintf('  act_bip           %s %s, bipolar %s\n', ...
        userdata.pulse_ep.surface_activation_kind, local_filled(userdata.surface.act_bip(:,1)), ...
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
fprintf('  named fields      %d surface fields, %d point properties\n', ...
        numel(userdata.surface.signalMaps), numel(userdata.electric.signalProps));

% --- 4. The geometry check ---------------------------------------------
% Area straight off the triangulation. If the 1-based conversion or the JSON
% round trip had gone wrong, this would not match what the server computes.
P  = tr.Points;
T  = tr.ConnectivityList;
v1 = P(T(:,2),:) - P(T(:,1),:);
v2 = P(T(:,3),:) - P(T(:,1),:);
areaFromTriRep = sum(0.5 * vecnorm(cross(v1, v2, 2), 2, 2)) / 100;   % mm^2 -> cm^2
fprintf('\nsurface area from triRep: %.2f cm2\n', areaFromTriRep);

% --- 5. Actual OpenEP analyses -----------------------------------------
% OpenEP is an optional, separately installed MATLAB library. These are its
% functions, not pulse-ep implementations with similar names.
if exist('getArea', 'file') ~= 2
    fprintf('\nAdd OpenEP to the MATLAB path to run the analysis section.\n');
else
    openepResults = struct('area_cm2', getArea(userdata));
    assert(abs(openepResults.area_cm2 - areaFromTriRep) < ...
           1e-8 * max(1, areaFromTriRep), 'OpenEP surface area differs.');
    fprintf('OpenEP surface area: %.6f cm2\n', openepResults.area_cm2);

    bipolar = userdata.surface.act_bip(:,2);
    if any(isfinite(bipolar))
        openepResults.mean_bipolar_mV = getMeanVoltage(userdata);
        openepResults.low_voltage_area_cm2 = ...
            getLowVoltageArea(userdata, 'threshold', [0 0.5]);
        % OpenEP selects whole triangles by their mean vertex voltage,
        % strictly between 0 and 0.5 mV. This is not subtriangle integration.
        faceVoltage = mean(bipolar(T), 2);
        triangleAreas = 0.5 * vecnorm(cross(v1, v2, 2), 2, 2) / 100;
        independentLowArea = sum(triangleAreas(faceVoltage > 0 & faceVoltage < 0.5));
        assert(abs(openepResults.low_voltage_area_cm2 - independentLowArea) < ...
               1e-8 * max(1, areaFromTriRep), 'OpenEP low-voltage area differs.');
        assert(abs(openepResults.mean_bipolar_mV - mean(bipolar, 'omitnan')) < 1e-10);
        fprintf('OpenEP mean bipolar voltage: %.6f mV\n', openepResults.mean_bipolar_mV);
        fprintf('OpenEP area with 0 < bipolar voltage < 0.5 mV: %.6f cm2\n', ...
                openepResults.low_voltage_area_cm2);
    end

    figure;
    if strcmp(userdata.pulse_ep.surface_activation_kind, 'pacemap_score') && ...
            any(isfinite(userdata.surface.act_bip(:,1))) && ~isempty(userdata.electric.egmX)
        drawMap(userdata, 'type', 'act');
        cb = findall(gcf, 'Type', 'ColorBar');
        cb.Label.String = 'Pace-match score (negative %)';
    elseif any(isfinite(bipolar)) && ~isempty(userdata.electric.egmX)
        drawMap(userdata, 'type', 'bip');
    else
        drawMap(userdata, 'type', 'none');
    end
    % OpenEP sets a white figure background, including under MATLAB's dark theme.
    set(findall(gcf, 'Type', 'ColorBar'), 'Color', [0 0 0]);
    title('OpenEP: map retrieved from pulse-ep via REST', 'Color', [0 0 0]);
end

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
