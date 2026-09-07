import io
from dataclasses import dataclass, field

import chardet
import numpy as np
import trimesh
from joblib import Parallel, delayed
from scipy.linalg import svd
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import NearestNeighbors


def _section_lines(data, start_index):
    """Return the right-hand side of every '='-containing line starting at start_index,
    stopping at the first line that has no '=' (section boundary)."""
    lines = []
    for line in data[start_index:]:
        if "=" not in line:
            break
        lines.append(line.split("=", 1)[1])
    return lines


def _section_body(data, section_name):
    """``(declared column names, index of the first data row)`` for a section.

    A CARTO section is a header, a run of ``;`` comment lines and then
    ``idx = v v v`` rows. The **last comment line names the columns** — the
    only place in the file that says what its numbers mean. Reading it is
    what separates ``Force`` from ``Paso`` when a future export reorders them.

    Comment lines are recognised by their leading ``;``, not by the absence of
    an ``=``: the colours section opens with ``; Color Value= -10000 …``.
    """
    start = find_section_index(data, section_name)
    names: list[str] = []
    i = start
    while i < len(data):
        stripped = data[i].strip()
        if stripped.startswith(";"):
            names = stripped.lstrip("; ").split()
        elif "=" in stripped:
            break
        i += 1
    return names, i


def _named_columns(values, names, kind_of_section):
    """Zip a value matrix with its declared column names.

    A file whose header does not describe every column falls back to
    positional ``<section>_<n>`` names rather than mislabelling: a wrong name
    on a clinical quantity is worse than no name.
    """
    if len(names) != values.shape[1]:
        if names:
            print(
                f"{kind_of_section}: {len(names)} declared names for "
                f"{values.shape[1]} columns — falling back to positional names"
            )
        names = [f"{kind_of_section}_{i}" for i in range(values.shape[1])]
    return dict(zip(names, values.T, strict=True))


@dataclass
class CartoMesh:
    """A parsed CARTO ``.mesh`` file: geometry plus its *named* per-vertex data.

    ``colors`` and ``attributes`` are keyed by the names the file declares
    (``Unipolar``, ``LAT``, ``Force``, ``Paso``, ``SCAR`` …). The column set
    differs between CARTO versions and map types, so reading them positionally
    both loses columns (``Paso``, ``µBi``, the whole attributes section) and
    risks reading one quantity out of another's slot.

    The legacy ``act_bip`` / ``uni_imp_frc`` arrays are still assembled — now
    by name, with the historical column positions as the fallback.
    """

    triangles: np.ndarray
    vertices: np.ndarray
    triangle_areas: np.ndarray
    is_vertex_at_edge: np.ndarray
    act_bip: np.ndarray
    normals: np.ndarray
    uni_imp_frc: np.ndarray | None
    #: per-vertex scalar columns of ``[VerticesColorsSection]``, by name
    colors: dict[str, np.ndarray] = field(default_factory=dict)
    #: per-vertex flags of ``[VerticesAttributesSection]`` (EML / SCAR …)
    attributes: dict[str, np.ndarray] = field(default_factory=dict)

    def as_tuple(self):
        """The historical 7-tuple of :func:`read_carto_mesh_file`."""
        return (
            self.triangles,
            self.vertices,
            self.triangle_areas,
            self.is_vertex_at_edge,
            self.act_bip,
            self.normals,
            self.uni_imp_frc,
        )


#: Legacy column positions, used only when the file declares no usable names.
_LEGACY_ACT_BIP = (2, 1)  # LAT, Bipolar
_LEGACY_UNI_IMP_FRC = (0, 3, 10)  # Unipolar, Impedance, Force


def parse_carto_mesh(filename) -> CartoMesh:
    """Read a CARTO ``.mesh`` file into a :class:`CartoMesh`."""
    # Detect file encoding, fall back to latin-1 (handles µ and other medical symbols)
    with open(filename, "rb") as f:
        raw = f.read(10000)
    detected = chardet.detect(raw).get("encoding") or "latin-1"

    try:
        with open(filename, encoding=detected) as file:
            data = file.readlines()
    except UnicodeDecodeError:
        with open(filename, encoding="latin-1") as file:
            data = file.readlines()

    # Check file version
    if "#TriangulatedMeshVersion2.0" not in data[0]:
        raise ValueError("Expected file format: #TriangulatedMeshVersion2.0")

    _, vertices_index = _section_body(data, "[VerticesSection]")
    _, triangles_index = _section_body(data, "[TrianglesSection]")
    color_names, vertex_colors_index = _section_body(data, "[VerticesColorsSection]")

    # Vertices — stop at first non-'=' line (section boundary), then batch-parse
    v_lines = _section_lines(data, vertices_index)
    if not v_lines:
        raise ValueError("No vertices found.")
    vertices = np.loadtxt(io.StringIO("\n".join(v_lines)), usecols=(0, 1, 2))
    print(f"Vertices found: {len(vertices)}")

    # Triangles — stop at first non-'=' line, filter active triangles (column 6 >= 0)
    t_lines = _section_lines(data, triangles_index)
    if not t_lines:
        raise ValueError("No triangles found.")
    # Load columns 0,1,2 (vertex indices) and column 6 (active flag)
    tri_cols = np.loadtxt(io.StringIO("\n".join(t_lines)), usecols=(0, 1, 2, 6), dtype=int)
    active_mask = tri_cols[:, 3] >= 0
    triangles = tri_cols[active_mask, :3]
    if len(triangles) == 0:
        raise ValueError("No active triangles found.")
    print(f"Faces found: {len(triangles)}")

    # Vertex colors — stop at first non-'=' line, replace sentinel -10000 with NaN
    c_lines = _section_lines(data, vertex_colors_index)
    if not c_lines:
        raise ValueError("No vertex colors found.")
    vertex_colors = np.loadtxt(io.StringIO("\n".join(c_lines)))
    vertex_colors[vertex_colors == -10000] = np.nan
    print(f"Colors found: {len(vertex_colors)} x {vertex_colors.shape[1]} ({color_names})")

    # Per-vertex flags (EML / extEML / SCAR). Optional: older exports and
    # anatomy-only meshes have no such section, which is not an error.
    attribute_values, attribute_names = None, []
    try:
        attribute_names, attributes_index = _section_body(data, "[VerticesAttributesSection]")
        a_lines = _section_lines(data, attributes_index)
        if a_lines:
            attribute_values = np.loadtxt(io.StringIO("\n".join(a_lines)))
            if attribute_values.ndim == 1:
                attribute_values = attribute_values[:, None]
    except ValueError:
        pass

    # Cleanup: drop vertices not referenced by any active triangle
    referenced_vertices = np.unique(triangles)  # already sorted

    filtered_vertices = vertices[referenced_vertices]
    filtered_vertex_colors = vertex_colors[referenced_vertices]

    # Remap triangle indices: np.searchsorted is O(N log N) vs dict lookup
    filtered_triangles = np.searchsorted(referenced_vertices, triangles)

    num_dropped_vertices = len(vertices) - len(filtered_vertices)
    print(f"Dropped unused vertices: {num_dropped_vertices}, remaining {len(filtered_vertices)}")
    num_dropped_colors = len(vertex_colors) - len(filtered_vertex_colors)
    print(f"Dropped unused colors: {num_dropped_colors}, remaining {len(filtered_vertex_colors)}")
    print(f"Dropped unused triangles: 0 - remaining {len(filtered_triangles)}")

    # Build trimesh with process=False — no vertices are removed
    mesh = trimesh.Trimesh(
        vertices=filtered_vertices, faces=filtered_triangles, convert_units="cm", process=False
    )

    # Find vertices at an edge
    is_vertex_at_edge = vertex_at_edge(mesh)

    # Vertex normals (trimesh built-in, no networkx needed)
    normals = calculate_vertex_normals(mesh)

    colors = _named_columns(filtered_vertex_colors, color_names, "color")

    attributes: dict[str, np.ndarray] = {}
    if attribute_values is not None and len(attribute_values) >= len(vertices):
        attributes = _named_columns(
            attribute_values[referenced_vertices], attribute_names, "attribute"
        )

    act_bip = _legacy_stack(colors, filtered_vertex_colors, ("LAT", "Bipolar"), _LEGACY_ACT_BIP)
    uni_imp_frc = _legacy_stack(
        colors, filtered_vertex_colors, ("Unipolar", "Impedance", "Force"), _LEGACY_UNI_IMP_FRC
    )
    if uni_imp_frc is None:
        print("Vertex colors does not have enough columns to extract the desired data.")

    triangle_areas = calculate_triangle_areas(filtered_vertices, filtered_triangles)

    return CartoMesh(
        triangles=filtered_triangles,
        vertices=filtered_vertices,
        triangle_areas=triangle_areas,
        is_vertex_at_edge=is_vertex_at_edge,
        act_bip=act_bip,
        normals=normals,
        uni_imp_frc=uni_imp_frc,
        colors=colors,
        attributes=attributes,
    )


def _legacy_stack(colors, values, names, positions):
    """Assemble a legacy column stack by name, falling back to position.

    The legacy arrays are still read directly by the figure and tagging code,
    so they keep their historical column order — but they are now filled from
    the columns the file *names*, not from the ones that happened to sit there
    in the exports this parser was written against.
    """
    if all(name in colors for name in names):
        return np.column_stack([colors[name] for name in names])
    if values.shape[1] > max(positions):
        return np.column_stack([values[:, p] for p in positions])
    return None


def read_carto_mesh_file(filename):
    """Legacy 7-tuple reader — see :func:`parse_carto_mesh` for named columns."""
    return parse_carto_mesh(filename).as_tuple()


def calculate_triangle_areas(vertices, triangles):
    """Vectorized triangle area calculation — avoids a Python loop over every face."""
    v0 = vertices[triangles[:, 0]]
    v1 = vertices[triangles[:, 1]]
    v2 = vertices[triangles[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    return 0.5 * np.linalg.norm(cross, axis=1)


def find_section_index(data, section_name):
    section_name_lower = section_name.lower()
    for i, line in enumerate(data):
        if line.lstrip().lower().startswith(section_name_lower):
            return i + 1
    raise ValueError(f"Section name {section_name} not found")


def vertex_at_edge(mesh):
    """Return a bool array marking every vertex that belongs to at least one face edge."""
    result = np.zeros(len(mesh.vertices), dtype=bool)
    result[mesh.faces.ravel()] = True
    return result


def calculate_vertex_normals(mesh):
    return mesh.vertex_normals


def compute_local_velocity(i, projected_coords, act_times, Vt, neighbours_model):
    # Get the nearest neighbours
    _, neighbours = neighbours_model.kneighbors([projected_coords[i]])

    # Use the neighbours to build a locally linear model of activation time
    model = LinearRegression().fit(projected_coords[neighbours[0]], act_times[neighbours[0]])

    # The velocity vector is the gradient of this model evaluated at (x_i, y_i)
    norm = np.linalg.norm(model.coef_)
    if norm == 0:
        # If the norm is zero, set the velocity to zero
        v_i = np.zeros_like(model.coef_)
    else:
        v_i = model.coef_ / norm

    # Reproject the velocity vector into 3D space
    return v_i @ Vt[:2]


def generate_conduct_velocity_vectors(mesh, scalars="activation_time"):
    # Get the activation times and coordinates from the mesh
    act_times = mesh.point_data[scalars]
    coords = mesh.points

    # Perform the SVD on the coordinates to obtain 2D projected coordinates
    _, _, Vt = svd(coords - coords.mean(axis=0), full_matrices=False)
    projected_coords = coords @ Vt[:2].T

    # Create a NearestNeighbors model for efficient nearest neighbors search
    neighbours_model = NearestNeighbors(n_neighbors=5).fit(projected_coords)

    # Compute the local 2D velocity vector at each point
    velocities = Parallel(n_jobs=-1)(
        delayed(compute_local_velocity)(i, projected_coords, act_times, Vt, neighbours_model)
        for i in range(projected_coords.shape[0])
    )

    # Normalize the velocity vectors to obtain unit vectors representing direction only
    directions = np.divide(
        velocities,
        np.linalg.norm(velocities, axis=1)[:, None],
        out=np.zeros_like(velocities),
        where=np.linalg.norm(velocities, axis=1)[:, None] != 0,
    )

    return np.array(velocities), np.array(directions)
