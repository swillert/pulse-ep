function [area, mask, surface] = pe_openep_ablation_area(userdata, varargin)
%PE_OPENEP_ABLATION_AREA OpenEP tag coverage, including small/empty selections.
%   [AREA, MASK, SURFACE] = PE_OPENEP_ABLATION_AREA(USERDATA, 'Radius', 5)
%   returns cm^2, a triangle mask and the covered triangulation. SURFACE is
%   [] when no triangle qualifies. RF markers must be selected explicitly
%   when fetching userdata. This is geometric coverage, not lesion size.
%
%   OpenEP's getAblationArea uses length(X) for an N-by-3 array, failing for
%   one or two tags. Duplicate positions in a working copy to reach three;
%   duplicates do not change the union of covered triangles. The caller's
%   data and marker count remain intact. Empty coverage is handled explicitly.
    p = inputParser;
    addParameter(p, 'Radius', 5, @(x) isnumeric(x) && isscalar(x) && isfinite(x) && x > 0);
    parse(p, varargin{:});
    if ~isfield(userdata, 'rfindex') || ~isfield(userdata.rfindex, 'tag')
        error('pulse_ep:MissingRFSelection', ...
            'Fetch userdata with AblationScope or AblationIds to select RF markers.');
    end
    tr = getMesh(userdata);
    if isempty(tr) || isempty(tr.Triangulation)
        error('pulse_ep:MissingMesh', 'A triangulated surface is required for tag coverage.');
    end
    X = userdata.rfindex.tag.X;
    mask = false(size(tr.Triangulation,1),1);
    area = 0; surface = [];
    if isempty(X); return; end
    if size(X,2) ~= 3 || any(~isfinite(X), 'all')
        error('pulse_ep:InvalidRFPositions', 'RF positions must be a finite N-by-3 array.');
    end
    prepared = userdata;
    if size(X,1) < 3
        prepared.rfindex.tag.X = [X; repmat(X(end,:),3-size(X,1),1)];
    end
    try
        [area, mask, surface] = getAblationArea(prepared, 'radius', p.Results.Radius);
    catch e
        % OpenEP tries to construct an empty triangulation when no centroid
        % is within radius. Other upstream failures must remain visible.
        if ~strcmp(e.identifier, 'MATLAB:triangulation:EmptyInputTriErrId')
            rethrow(e);
        end
    end
end
