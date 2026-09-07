function filename = build_toolbox(outputDirectory)
%BUILD_TOOLBOX Package only the public MATLAB client files (MATLAB R2023a+).
%   Run from the source archive: addpath('examples/matlab'); build_toolbox;
%   The output defaults to dist/pulse_ep_matlab-VERSION.mltbx.
    folder = fileparts(mfilename('fullpath'));
    root = fileparts(fileparts(folder));
    if nargin == 0; outputDirectory = fullfile(root,'dist'); end
    if ~exist(outputDirectory,'dir'); mkdir(outputDirectory); end
    version = regexp(fileread(fullfile(root,'pyproject.toml')), ...
                     '(?m)^version = "([^"]+)"','tokens','once');
    if isempty(version); error('pulse_ep:MissingVersion','No project version found.'); end
    stage = tempname; mkdir(stage);
    cleanup = onCleanup(@() rmdir(stage,'s')); %#ok<NASGU>
    files = dir(fullfile(folder,'**','*.m'));
    for i = 1:numel(files)
        if strcmp(files(i).name,'build_toolbox.m'); continue; end
        relative = erase(fullfile(files(i).folder,files(i).name),[folder filesep]);
        target = fullfile(stage,relative);
        if ~exist(fileparts(target),'dir'); mkdir(fileparts(target)); end
        copyfile(fullfile(files(i).folder,files(i).name),target);
    end
    copyfile(fullfile(root,'LICENSE'),fullfile(stage,'LICENSE'));
    copyfile(fullfile(folder,'README.md'),fullfile(stage,'README.md'));
    copyfile(fullfile(root,'docs','guides','matlab.md'),fullfile(stage,'GUIDE.md'));
    copyfile(fullfile(root,'docs','guides','openep.md'),fullfile(stage,'openep.md'));
    readme = fileread(fullfile(stage,'README.md'));
    readme = strrep(readme,'../../docs/guides/matlab.md','GUIDE.md');
    readme = strrep(readme,'../../docs/guides/openep.md','openep.md');
    readme = strrep(readme,'../../docs/','https://github.com/swillert/pulse-ep/blob/main/docs/');
    readme = strrep(readme,'../README.md','https://github.com/swillert/pulse-ep/blob/main/examples/README.md');
    fid = fopen(fullfile(stage,'README.md'),'w');
    closer = onCleanup(@() fclose(fid));
    fprintf(fid,'%s',readme); clear closer;
    % Stable identity lets MATLAB recognize later versions as updates.
    opts = matlab.addons.toolbox.ToolboxOptions(stage,'e59d064c-9464-4b09-bd07-f9b26280457a');
    opts.ToolboxName = 'pulse-ep MATLAB';
    opts.ToolboxVersion = version{1};
    opts.AuthorName = 'Sven Willert';
    opts.AuthorEmail = 'sw@willert.net';
    opts.Summary = 'Access electroanatomical mapping studies through the pulse-ep REST API.';
    opts.Description = 'MATLAB functions and an optional session client for studies, maps, measurements, waveforms and OpenEP export. OpenEP is installed separately.';
    opts.MinimumMatlabRelease = 'R2020a';
    opts.ToolboxMatlabPath = stage;
    opts.RequiredAddons = struct.empty;
    opts.RequiredAdditionalSoftware = struct.empty;
    filename = fullfile(outputDirectory,['pulse_ep_matlab-' version{1} '.mltbx']);
    opts.OutputFile = filename;
    matlab.addons.toolbox.packageToolbox(opts);
    fprintf('Created %s\n', filename);
end
