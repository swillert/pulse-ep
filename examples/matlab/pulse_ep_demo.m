% PULSE_EP_DEMO  End-to-end MATLAB example for pulse-ep.
%
%   1. Logs in and lists studies.
%   2. Picks the first map in the first study (override with PE_MAP_ID).
%   3. Renders the mesh with trisurf and the catheter points with scatter3.
%   4. Plots a histogram of the per-vertex scalar field.
%
%   Requires MATLAB R2020a or newer. Run with:
%     pulse_ep_demo
%
%   Environment variables read (see ../README.md):
%     PULSE_EP_BASE_URL   default http://127.0.0.1:5000
%     PULSE_EP_USERNAME   default admin
%     PULSE_EP_PASSWORD   required

baseURL  = getenv('PULSE_EP_BASE_URL');
if isempty(baseURL); baseURL = 'http://127.0.0.1:5000'; end
username = getenv('PULSE_EP_USERNAME');
if isempty(username); username = 'admin'; end
password = getenv('PULSE_EP_PASSWORD');
if isempty(password)
    error('PULSE_EP_PASSWORD is not set. See examples/README.md.');
end

% --- 1. Login & list studies -------------------------------------------
token   = pe_login(baseURL, username, password);
studies = pe_list_studies(baseURL, token);
if isempty(studies)
    error('No studies in the database.');
end
fprintf('Found %d study/studies.\n', numel(studies));

% --- 2. Pick a map ------------------------------------------------------
mapIdEnv = getenv('PE_MAP_ID');
if ~isempty(mapIdEnv)
    mapId = str2double(mapIdEnv);
    fprintf('Using PE_MAP_ID = %d from environment.\n', mapId);
else
    maps = pe_list_maps(baseURL, token, studies(1).id);
    if isempty(maps)
        error('Study has no EP maps.');
    end
    mapId = maps(1).id;
    fprintf('Using first map of first study: id=%d ("%s")\n', ...
            mapId, maps(1).map_name);
end

% --- 3. Fetch mesh ------------------------------------------------------
mesh = pe_get_mesh(baseURL, token, mapId, '', 5.0);   % '' -> the map's primary quantity
fprintf('Mesh: %d vertices, %d triangles, scalar non-NaN = %d/%d.\n', ...
        size(mesh.vertices, 1), size(mesh.faces, 1), ...
        sum(~isnan(mesh.scalars)), numel(mesh.scalars));

% --- 4. Render ----------------------------------------------------------
figure('Name', sprintf('pulse-ep map %d', mapId), 'Color', 'w');

subplot(1, 2, 1);
trisurf(mesh.faces, mesh.vertices(:, 1), mesh.vertices(:, 2), ...
        mesh.vertices(:, 3), mesh.scalars, 'EdgeColor', 'none');
axis equal vis3d;
lighting gouraud; camlight headlight;
colormap(turbo);
colorbar;
title(sprintf('Mesh (scalar = act, map %d)', mapId));

if ~isempty(mesh.points)
    hold on;
    scatter3(mesh.points(:, 1), mesh.points(:, 2), mesh.points(:, 3), ...
             8, 'k', 'filled', 'MarkerFaceAlpha', 0.5);
    hold off;
end

% --- 5. Histogram -------------------------------------------------------
subplot(1, 2, 2);
histogram(mesh.scalars(~isnan(mesh.scalars)), 40);
xlabel('Scalar value');
ylabel('Vertex count');
title(sprintf('Scalar distribution — map %d', mapId));
grid on;

exportgraphics(gcf, 'pulse_ep_demo.png', 'Resolution', 150);
fprintf('Wrote pulse_ep_demo.png\n');
