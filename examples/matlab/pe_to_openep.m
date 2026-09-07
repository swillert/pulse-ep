function userdata = pe_to_openep(baseURL, token, mapId, includePoints)
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
%   The point of doing this at all: pulse-ep reads EnSite X exports and OpenEP
%   does not, so a map from either vendor can go through any OpenEP analysis
%   once it is in this shape.
%
%   The mapping from pulse-ep's declared quantities onto OpenEP's positional
%   slots happens server-side, where tests pin it. What is left here is what
%   JSON cannot express: matrices arrive as nested arrays and `triRep` has to
%   become a MATLAB triangulation object.
%
%   Example:
%       token    = pe_login("http://localhost:5000", "user", "pw");
%       userdata = pe_to_openep("http://localhost:5000", token, 12);
%       drawMap(userdata);                 % an OpenEP function
%
%   READ THE NOTES. userdata.notes records everything the structure could not
%   carry — an empty slot, a quantity OpenEP's surface has no room for, and in
%   particular a pace-mapping score that was deliberately *not* put into the
%   activation-time column. Those slots are NaN rather than filled, because a
%   gap can be seen and a plausible wrong number cannot.
%
%   See also: pe_login, pe_get_mesh, https://openep.io/api/

    if nargin < 4; includePoints = true; end

    opts = weboptions('HeaderFields', ...
           {'Authorization', char(strcat("Bearer ", token))}, ...
           'ContentType', 'json', 'Timeout', 120);
    raw = webread(strcat(baseURL, "/epmaps/", string(mapId), "/openep"), opts, ...
                  'include_points', string(double(includePoints)));

    userdata = raw;
    userdata.surface.triRep       = local_triangulation(raw.surface.triRep);
    userdata.surface.act_bip      = local_matrix(raw.surface.act_bip);
    userdata.surface.uni_imp_frc  = local_matrix(raw.surface.uni_imp_frc);
    userdata.surface.isVertexAtRim = logical(local_matrix(raw.surface.isVertexAtRim));

    userdata.electric.egmX = local_matrix(raw.electric.egmX);
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
