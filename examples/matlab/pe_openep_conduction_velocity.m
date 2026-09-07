function [speed, pointIndices] = pe_openep_conduction_velocity(userdata, varargin)
%PE_OPENEP_CONDUCTION_VELOCITY Run OpenEP with physical LAT in milliseconds.
%   SPEED = PE_OPENEP_CONDUCTION_VELOCITY(USERDATA) uses finite activation-time
%   measurements and the stored point coordinates. Pace scores are excluded.
%   ...,'Indices',I restricts the input to a chosen set of measurement points.
%   SPEED has one value per mesh vertex, in m/s. This is OpenEP's spatial RBF
%   estimate; signal availability alone does not validate its physiological use.
%
%   Upstream getConductionVelocity reads mapAnnot directly, without removing
%   per-point reference offsets or accounting for sampling frequency. Work on
%   a copy with physical LAT in ms and a common zero reference.
    p = inputParser;
    addParameter(p, 'Indices', 1:size(userdata.electric.egmX, 1));
    parse(p, varargin{:});
    if ~isfield(userdata, 'pulse_ep') || ~isfield(userdata.pulse_ep, 'lat_ms')
        error('pulse_ep:MissingLAT', 'Fetch a current pulse-ep OpenEP export containing lat_ms.');
    end
    lat = userdata.pulse_ep.lat_ms(:);
    X = userdata.electric.egmX;
    pointIndices = p.Results.Indices(:);
    if any(pointIndices < 1 | pointIndices > numel(lat) | pointIndices ~= fix(pointIndices))
        error('pulse_ep:InvalidIndices', 'Indices must identify measurement points.');
    end
    valid = isfinite(lat(pointIndices)) & all(isfinite(X(pointIndices,:)), 2);
    a = userdata.electric.annotations;
    offset = a.mapAnnot(pointIndices) - a.referenceAnnot(pointIndices);
    woi = a.woi(pointIndices,:);
    knownWindow = all(isfinite(woi), 2);
    valid = valid & (~knownWindow | (offset >= woi(:,1) & offset <= woi(:,2)));
    pointIndices = pointIndices(valid);
    if numel(pointIndices) < 4
        error('pulse_ep:MissingLAT', 'At least four finite activation-time points are required; pace scores cannot be used.');
    end
    selected = X(pointIndices,:);
    if size(unique(selected, 'rows'), 1) ~= size(selected, 1)
        error('pulse_ep:DuplicatePositions', 'Select points with distinct positions using Indices.');
    end
    if rank([ones(size(selected,1),1), selected]) < 4
        error('pulse_ep:DegeneratePositions', 'OpenEP RBF interpolation requires nondegenerate 3-D positions.');
    end
    prepared = userdata;
    prepared.electric.egmX = selected;
    prepared.electric.annotations.mapAnnot = lat(pointIndices);
    prepared.electric.annotations.referenceAnnot = zeros(numel(pointIndices), 1);
    prepared.electric.annotations.woi = repmat([-Inf Inf], numel(pointIndices), 1);
    prepared.electric.sampleFrequency = 1000;
    speed = getConductionVelocity(prepared);
end
