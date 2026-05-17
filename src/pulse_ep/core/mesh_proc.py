import io
import numpy as np
import trimesh
import chardet
from scipy.spatial import cKDTree
from scipy.linalg import svd
from scipy.spatial.distance import cdist
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import NearestNeighbors
from joblib import Parallel, delayed
from sklearn.cluster import KMeans

def _section_lines(data, start_index):
    """Return the right-hand side of every '='-containing line starting at start_index,
    stopping at the first line that has no '=' (section boundary)."""
    lines = []
    for line in data[start_index:]:
        if '=' not in line:
            break
        lines.append(line.split('=', 1)[1])
    return lines


def read_carto_mesh_file(filename):
    # Detect file encoding, fall back to latin-1 (handles µ and other medical symbols)
    with open(filename, 'rb') as f:
        raw = f.read(10000)
    detected = chardet.detect(raw).get('encoding') or 'latin-1'

    try:
        with open(filename, 'r', encoding=detected) as file:
            data = file.readlines()
    except UnicodeDecodeError:
        with open(filename, 'r', encoding='latin-1') as file:
            data = file.readlines()

    # Check file version
    if '#TriangulatedMeshVersion2.0' not in data[0]:
        raise ValueError('Expected file format: #TriangulatedMeshVersion2.0')

    # Find the vertices and triangles sections
    vertices_index = find_section_index(data, '[VerticesSection]')+2
    triangles_index = find_section_index(data, '[TrianglesSection]')+2
    vertex_colors_index = find_section_index(data, '[VerticesColorsSection]')+3

    # Vertices — stop at first non-'=' line (section boundary), then batch-parse
    v_lines = _section_lines(data, vertices_index)
    if not v_lines:
        raise ValueError('No vertices found.')
    vertices = np.loadtxt(io.StringIO('\n'.join(v_lines)), usecols=(0, 1, 2))
    print(f"Vertices found: {len(vertices)}")

    # Triangles — stop at first non-'=' line, filter active triangles (column 6 >= 0)
    t_lines = _section_lines(data, triangles_index)
    if not t_lines:
        raise ValueError('No triangles found.')
    # Load columns 0,1,2 (vertex indices) and column 6 (active flag)
    tri_cols = np.loadtxt(io.StringIO('\n'.join(t_lines)), usecols=(0, 1, 2, 6), dtype=int)
    active_mask = tri_cols[:, 3] >= 0
    triangles = tri_cols[active_mask, :3]
    if len(triangles) == 0:
        raise ValueError('No active triangles found.')
    print(f"Faces found: {len(triangles)}")

    # Vertex colors — stop at first non-'=' line, replace sentinel -10000 with NaN
    c_lines = _section_lines(data, vertex_colors_index)
    if not c_lines:
        raise ValueError('No vertex colors found.')
    vertex_colors = np.loadtxt(io.StringIO('\n'.join(c_lines)))
    vertex_colors[vertex_colors == -10000] = np.nan
    print(f"Colors found: {len(vertex_colors)}")

    # Cleanup: drop vertices not referenced by any active triangle
    referenced_vertices = np.unique(triangles)   # already sorted

    filtered_vertices      = vertices[referenced_vertices]
    filtered_vertex_colors = vertex_colors[referenced_vertices]

    # Remap triangle indices: np.searchsorted is O(N log N) vs dict lookup
    filtered_triangles = np.searchsorted(referenced_vertices, triangles)

    num_dropped_vertices = len(vertices) - len(filtered_vertices)
    print(f"Dropped unused vertices: {num_dropped_vertices}, remaining {len(filtered_vertices)}")
    num_dropped_colors = len(vertex_colors) - len(filtered_vertex_colors)
    print(f"Dropped unused colors: {num_dropped_colors}, remaining {len(filtered_vertex_colors)}")
    print(f"Dropped unused triangles: 0 - remaining {len(filtered_triangles)}")

    # Build trimesh with process=False — no vertices are removed
    mesh = trimesh.Trimesh(vertices=filtered_vertices, faces=filtered_triangles,
                           convert_units='cm', process=False)

    # Find vertices at an edge
    is_vertex_at_edge = vertex_at_edge(mesh)

    # Vertex normals (trimesh built-in, no networkx needed)
    normals = calculate_vertex_normals(mesh)

    act_bip = np.column_stack((filtered_vertex_colors[:, 2], filtered_vertex_colors[:, 1]))

    if filtered_vertex_colors.shape[1] >= 11:
        uni_imp_frc = np.column_stack((filtered_vertex_colors[:, 0],
                                       filtered_vertex_colors[:, 3],
                                       filtered_vertex_colors[:, 10]))
    else:
        print("Vertex colors does not have enough columns to extract the desired data.")
        uni_imp_frc = None

    triangle_areas = calculate_triangle_areas(filtered_vertices, filtered_triangles)

    return filtered_triangles, filtered_vertices, triangle_areas, is_vertex_at_edge, act_bip, normals, uni_imp_frc

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
    raise ValueError(f'Section name {section_name} not found')

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

def generate_conduct_velocity_vectors(mesh, scalars="act"):
    # Get the activation times and coordinates from the mesh
    act_times = mesh.point_data[scalars]
    coords = mesh.points

    # Perform the SVD on the coordinates to obtain 2D projected coordinates
    _, _, Vt = svd(coords - coords.mean(axis=0), full_matrices=False)
    projected_coords = coords @ Vt[:2].T

    # Create a NearestNeighbors model for efficient nearest neighbors search
    neighbours_model = NearestNeighbors(n_neighbors=5).fit(projected_coords)

    # Compute the local 2D velocity vector at each point
    velocities = Parallel(n_jobs=-1)(delayed(compute_local_velocity)(i, projected_coords, act_times, Vt, neighbours_model) for i in range(projected_coords.shape[0]))

    # Normalize the velocity vectors to obtain unit vectors representing direction only
    directions = np.divide(velocities, np.linalg.norm(velocities, axis=1)[:, None],
                           out=np.zeros_like(velocities), where=np.linalg.norm(velocities, axis=1)[:, None]!=0)

    return np.array(velocities), np.array(directions)
