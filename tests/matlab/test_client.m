function tests = test_client
%TEST_CLIENT Native integration tests against the disposable synthetic service.
    tests = functiontests(localfunctions);
end

function setupOnce(t)
    t.TestData.base = getenv('PULSE_EP_BASE_URL');
    t.TestData.user = getenv('PULSE_EP_USERNAME');
    t.TestData.password = getenv('PULSE_EP_PASSWORD');
    t.TestData.cfg = jsondecode(fileread(getenv('PULSE_EP_TEST_CONFIG')));
    t.TestData.client = pulseep.Client(t.TestData.base);
    t.TestData.token = pe_login(t.TestData.base,t.TestData.user,t.TestData.password);
end

function setup(t)
    t.TestData.client.useToken(t.TestData.token);
end

function testLoginAndLogout(t)
    pe = pulseep.Client([t.TestData.base '/']);
    t.verifyFalse(pe.isLoggedIn());
    t.verifyError(@() pe.studies(),'pulse_ep:NotLoggedIn');
    pe.login(t.TestData.user,t.TestData.password);
    t.verifyTrue(pe.isLoggedIn());
    t.verifyEqual(pe.BaseURL,string(t.TestData.base));
    pe.logout(); t.verifyFalse(pe.isLoggedIn());
end

function testStudyAndMapTables(t)
    pe = t.TestData.client;cfg=t.TestData.cfg;
    studies = pe.studies();t.verifyClass(studies,'table');t.verifyEqual(height(studies),4);
    t.verifyEqual(sort(studies.Properties.VariableNames),sort({'id','study_name','vendor'}));
    maps=pe.maps(cfg.carto.study);t.verifyEqual(height(maps),1);
    t.verifyEqual(maps.id,cfg.carto.map);t.verifyEqual(maps.measurement_points,64);
    empty=pe.maps(cfg.empty_study);t.verifyClass(empty,'table');t.verifyEmpty(empty);
    t.verifyEqual(empty.Properties.VariableNames,maps.Properties.VariableNames);
end

function testSelectionsAndDirectFunctionParity(t)
    pe=t.TestData.client;id=t.TestData.cfg.carto.map;
    full=pe.loadMap(id);
    old=pe_get_mesh(t.TestData.base,t.TestData.token,id,'',5,'raw');
    t.verifyEqual(full.vertices,old.vertices);t.verifyEqual(full.faces,old.faces);
    t.verifyEqual(full.data.mesh_data,old.data.mesh_data);
    t.verifyEqual(full.data.point_data,old.data.point_data);
    mesh=pe.loadMap(id,'Include',{'mesh'});
    t.verifyEqual(mesh.vertices,full.vertices);t.verifyEqual(mesh.faces,full.faces);
    t.verifyFalse(isfield(mesh.data,'point_data'));t.verifyFalse(isfield(mesh.data,'waveforms'));
    t.verifyFalse(isfield(mesh.data.mesh_data,'scalar_fields'));t.verifyEmpty(mesh.scalars);
    meta=pe.loadMap(id,'Include',{});
    t.verifyEmpty(meta.vertices);t.verifySize(meta.vertices,[0 3]);
    t.verifyFalse(isfield(meta.data,'mesh_data'));t.verifyEmpty(meta.data.selection.included);
    fields=pe.loadMap(id,'Include',{'fields'});
    t.verifyEmpty(fields.vertices);t.verifyEqual(fields.data.mesh_data.scalar_fields,full.data.mesh_data.scalar_fields);
    points=pe.loadMap(id,'Include',{'points'});
    t.verifyEmpty(points.faces);t.verifyEqual(points.points,full.points);
    t.verifyEqual(points.data.point_data.measurement_points,full.data.point_data.measurement_points);
    t.verifyEqual(double(full.faces)-1,full.data.mesh_data.faces);
end

function testEnsiteAndPointOnlyMaps(t)
    pe=t.TestData.client;cfg=t.TestData.cfg;
    m=pe.loadMap(cfg.ensite.map,'Include',{'mesh','fields','points'});
    t.verifySize(m.vertices,[962 3]);t.verifySize(m.faces,[1920 3]);
    t.verifySize(m.points,[64 3]);
    point=pe.loadMap(cfg.signal.map);
    t.verifySize(point.vertices,[0 3]);t.verifySize(point.faces,[0 3]);
    t.verifySize(point.points,[1 3]);
    t.verifyTrue(isfield(point.data,'placed_points'));
end

function testPointPagingAndFieldDiscovery(t)
    pe=t.TestData.client;id=t.TestData.cfg.carto.map;
    p=pe.points(id,'Limit',2,'Offset',1);
    t.verifyEqual(p.count,64);t.verifyEqual(p.returned,2);t.verifyEqual(p.offset,1);
    all=pe.points(id,'Limit',0);t.verifyEqual(all.returned,64);
    fields=pe.scalars(id);t.verifyFalse(isempty(fields.scalars));
    m=pe.loadMap(id,'Include',{'fields'},'ScalarName',fields.primary);
    t.verifyEqual(numel(m.scalars),962);
end

function testWaveformDownload(t)
    pe=t.TestData.client;cfg=t.TestData.cfg;
    metadata=pe.waveforms(cfg.signal.map);t.verifyEqual(metadata.count,1);
    filename=[tempname '.parquet'];cleanup=onCleanup(@() delete(filename)); %#ok<NASGU>
    pe.downloadWaveform(cfg.signal.waveform,filename);
    samples=parquetread(filename);
    t.verifyEqual(samples.BIP,[1;2;3;4]);t.verifyEqual(samples.V1,[10;20;30;40]);
end

function testOpenEPUsesTheExistingConverter(t)
    pe=t.TestData.client;id=t.TestData.cfg.signal.map;
    u=pe.openep(id,'IncludeSignals',true,'ECGChannels',{'V1'},'AblationScope','study');
    direct=pe_to_openep(t.TestData.base,t.TestData.token,id,true, ...
                       'IncludeSignals',true,'ECGChannels',{'V1'},'AblationScope','study');
    t.verifyEqual(u,direct);t.verifyEqual(u.electric.egm,[1 2 3 4]);
    t.verifyEqual(u.electric.sampleFrequency,1000);t.verifyEqual(u.rfindex.tag.X,[0 1 2]);
    mesh=pe.openep(t.TestData.cfg.carto.map,'IncludePoints',false);
    t.verifyClass(mesh.surface.triRep,'triangulation');t.verifyEmpty(mesh.electric.names);
end

function testAreaFunctionParity(t)
    pe=t.TestData.client;id=t.TestData.cfg.ensite.map;intervals=[0 .5;.5 5];
    actual=pe.areas(id,intervals,'ScalarName','voltage_bipolar');
    expected=pe_areas_per_interval(t.TestData.base,t.TestData.token,id,intervals,'voltage_bipolar',5);
    t.verifyEqual(actual,expected);t.verifyEqual(numel(actual),2);
end

function testExpiredAuthenticationIsCleared(t)
    pe=t.TestData.client;pe.useToken(t.TestData.cfg.expired_token);
    t.verifyError(@() pe.studies(),'pulse_ep:AuthenticationRequired');
    t.verifyFalse(pe.isLoggedIn());
end

function testCredentialsAreTransient(t)
    pe=t.TestData.client;
    filename=[tempname '.mat'];cleanup=onCleanup(@() delete(filename)); %#ok<NASGU>
    save(filename,'pe');loaded=load(filename);
    t.verifyEqual(loaded.pe.BaseURL,pe.BaseURL);
    t.verifyFalse(loaded.pe.isLoggedIn());t.verifyTrue(pe.isLoggedIn());
end

function testInvalidSelectionsAndIDs(t)
    pe=t.TestData.client;id=t.TestData.cfg.carto.map;
    t.verifyError(@() pe.loadMap(id,'Include',{'signals'}),'pulse_ep:InvalidSelection');
    t.verifyError(@() pulseep.Client('https://user:password@host'),'pulse_ep:InvalidURL');
    t.verifyError(@() pulseep.Client('https://host?token=secret'),'pulse_ep:InvalidURL');
    t.verifyError(@() pe.useToken(''),'pulse_ep:InvalidToken');
    t.verifyTrue(pe.isLoggedIn());
end
