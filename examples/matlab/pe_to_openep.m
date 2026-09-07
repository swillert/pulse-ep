function userdata = pe_to_openep(baseURL, token, mapId, includePoints, varargin)
%PE_TO_OPENEP  Fetch one map as an OpenEP `userdata` structure.
%
%   userdata = PE_TO_OPENEP(baseURL, token, mapId) reads GET
%   /epmaps/<id>/openep and returns the structure OpenEP's analysis functions
%   take. It is a REST client like pe_get_mesh and the rest of this directory:
%   no database credential, no file handed over out of band.
%
%   userdata = PE_TO_OPENEP(..., false) omits the measurement points, leaving
%   geometry and the per-vertex quantities.
%
%   Maps from either vendor can use OpenEP analyses supported by the exported
%   quantities. Add 'IncludeSignals',true for stored point-linked signals.
%   Select RF markers with 'AblationScope','study' or 'AblationIds',[...].
%   'ECGChannels',{'V1','V2'} selects leads; 'SignalScaleToMV',factor applies
%   an explicitly known calibration to amplitudes whose units are unknown.
%
%   The mapping from pulse-ep's declared quantities onto OpenEP's positional
%   slots happens server-side, where tests pin it. What is left here is what
%   JSON cannot express: matrices arrive as nested arrays and `triRep` has to
%   become a MATLAB triangulation object.
%
%   Example:
%       token    = pe_login("http://localhost:5000", "user", "pw");
%       userdata = pe_to_openep("http://localhost:5000", token, 12);
%       drawMap(userdata, 'type', 'bip');   % for a map with bipolar voltage
%
%   Pace maps use negative scores in surface.act_bip(:,1), and the same
%   convention in mapAnnot - referenceAnnot. userdata.pulse_ep records the
%   quantity and encoding: these are percentages, not activation times.
%   userdata.notes records missing quantities and reconstructed references.
%
%   See also: pe_login, pe_get_mesh, https://openep.io/api/

    if nargin < 4; includePoints = true; end
    p = inputParser;
    addParameter(p, 'IncludeSignals', false);
    addParameter(p, 'AblationScope', 'none');
    addParameter(p, 'AblationIds', []);
    addParameter(p, 'ECGChannels', {});
    addParameter(p, 'SignalScaleToMV', []);
    parse(p, varargin{:});
    query = {'include_points', string(double(includePoints)), ...
             'include_signals', string(double(p.Results.IncludeSignals)), ...
             'ablation_scope', p.Results.AblationScope};
    if ~isempty(p.Results.AblationIds)
        query = [query, {'ablation_ids', strjoin(string(p.Results.AblationIds), ',')}];
    end
    if ~isempty(p.Results.ECGChannels)
        query = [query, {'ecg_channels', strjoin(string(p.Results.ECGChannels), ',')}];
    end
    if ~isempty(p.Results.SignalScaleToMV)
        query = [query, {'signal_scale_to_mv', string(p.Results.SignalScaleToMV)}];
    end

    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 300);
    raw = webread(strcat(baseURL, "/epmaps/", string(mapId), "/openep"), opts, query{:});

    userdata = raw;
    userdata.surface.triRep       = local_triangulation(raw.surface.triRep);
    userdata.surface.act_bip      = local_matrix(raw.surface.act_bip);
    userdata.surface.uni_imp_frc  = local_matrix(raw.surface.uni_imp_frc);
    userdata.surface.isVertexAtRim = logical(local_matrix(raw.surface.isVertexAtRim));
    if isfield(raw.surface, 'normals')
        userdata.surface.normals = local_matrix(raw.surface.normals);
    end
    if isfield(raw.surface, 'signalMaps')
        userdata.surface.signalMaps = local_records(raw.surface.signalMaps, 'map');
    end
    if isfield(raw.electric, 'signalProps')
        userdata.electric.signalProps = local_records(raw.electric.signalProps, 'value');
    end

    userdata.electric.egmX = local_matrix(raw.electric.egmX);
    n = size(userdata.electric.egmX, 1);
    userdata.electric.names = cellstr(string(raw.electric.names(:)));
    if isempty(raw.electric.tags)
        userdata.electric.tags = repmat({cell(0, 1)}, n, 1);
    else
        userdata.electric.tags = cell(n, 1);
        for i = 1:n
            tags = raw.electric.tags{i};
            if isempty(tags)
                userdata.electric.tags{i} = cell(0, 1);
            else
                userdata.electric.tags{i} = cellstr(string(tags(:)));
            end
        end
    end
    for f = ["egm", "egmUni", "egmRef", "egmRef2", "ecg", "egmUniX"]
        if isfield(raw.electric, f)
            if f == "ecg" && isempty(raw.electric.ecgNames)
                % Nested empty JSON arrays cannot retain a zero third axis.
                userdata.electric.ecg = nan(n, size(userdata.electric.egm, 2), 0);
            else
                userdata.electric.(f) = local_matrix(raw.electric.(f));
            end
        end
    end
    for f = ["force", "axialAngle", "lateralAngle", "time_force", "time_axial", "time_lateral"]
        userdata.electric.force.(f) = local_matrix(raw.electric.force.(f));
    end
    if isfield(raw, 'rfindex')
        userdata.rfindex.tag.X = local_matrix(raw.rfindex.tag.X);
    end
    for f = ["egmSurfX", "barDirection"]
        if isfield(raw.electric, f)
            userdata.electric.(f) = local_matrix(raw.electric.(f));
        end
    end
    for f = ["bipolar", "unipolar"]
        userdata.electric.voltages.(f) = local_matrix(raw.electric.voltages.(f));
    end
    for f = ["referenceAnnot", "mapAnnot", "woi"]
        userdata.electric.annotations.(f) = local_matrix(raw.electric.annotations.(f));
    end

    if isfield(userdata, 'notes') && ~isempty(userdata.notes)
        fprintf('pulse-ep notes on this map:\n');
        fprintf('  %s\n', string(userdata.notes));
    end
end

function entries = local_records(raw, valueField)
%LOCAL_RECORDS Keep OpenEP's cell-of-struct convention for zero/one/many fields.
    if isempty(raw)
        entries = cell(0, 1);
    elseif isstruct(raw)
        entries = num2cell(raw(:));
    else
        entries = raw(:);
    end
    for i = 1:numel(entries)
        values = local_matrix(entries{i}.(valueField));
        entries{i}.(valueField) = values(:);
        if isfield(entries{i}, 'statusMask')
            mask = local_matrix(entries{i}.statusMask);
            entries{i}.statusMask = logical(mask(:));
        end
    end
end

function m = local_matrix(value)
%LOCAL_MATRIX  Nested JSON arrays back into a numeric matrix.
%   An empty slot arrives as null, which webread gives as [] inside a cell;
%   those become NaN again, which is what they meant on the way out.
    if isnumeric(value) || islogical(value)
        m = double(value);
        return
    end
    if iscell(value)
        rows = cellfun(@(r) local_row(r), value, 'UniformOutput', false);
        m = vertcat(rows{:});
        return
    end
    m = double(value);
end

function r = local_row(row)
    if iscell(row)
        row = cellfun(@(v) local_scalar(v), row);
    end
    r = double(reshape(row, 1, []));
end

function s = local_scalar(value)
    if isempty(value); s = NaN; else; s = double(value); end
end

function tr = local_triangulation(triRep)
%LOCAL_TRIANGULATION  Build the object JSON cannot carry.
%   Indices arrive 1-based: pulse-ep counts vertices from zero and converts on
%   the way out, so this is not the place that boundary is crossed.
    X = local_matrix(triRep.X);
    T = local_matrix(triRep.Triangulation);
    if isempty(T) || isempty(X)
        tr = [];
    else
        tr = triangulation(double(T), double(X));
    end
end
