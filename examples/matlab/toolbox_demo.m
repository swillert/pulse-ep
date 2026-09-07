% Login credentials are read from the process environment.
pe = pulseep.Client(getenv('PULSE_EP_BASE_URL'));
pe.login(getenv('PULSE_EP_USERNAME'),getenv('PULSE_EP_PASSWORD'));
studies = pe.studies();
disp(studies);
if isempty(studies); error('pulse_ep:NoStudies','No studies are available.'); end
maps = table();
for studyRow = 1:height(studies)
    maps = pe.maps(studies.id(studyRow));
    if ~isempty(maps); break; end
end
disp(maps);
if isempty(maps); error('pulse_ep:NoMaps','No study contains a map.'); end
mapId = maps.id(1);
if ~isempty(getenv('PE_MAP_ID')); mapId = str2double(getenv('PE_MAP_ID')); end
map = pe.loadMap(mapId,'Include',{'mesh','fields','points'});
fprintf('Loaded %d vertices, %d triangles and %d measurement positions.\n', ...
         size(map.vertices,1),size(map.faces,1),size(map.points,1));
disp(pe.scalars(mapId));
pe.logout();
