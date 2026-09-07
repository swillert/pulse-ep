"""The CARTO mesh reader must take its per-vertex columns by name.

Reading them by position dropped every column past the three the reader knew
about — ``Paso`` (the pace-match score), ``µBi``, and the whole
``[VerticesAttributesSection]`` — and would silently mis-assign the rest in an
export that ordered them differently.
"""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.importers.carto import register_carto_scalars
from pulse_ep.core.mesh_proc import parse_carto_mesh, read_carto_mesh_file

# A minimal but structurally faithful mesh: two triangles over four vertices,
# with the header layout a real CARTO 3 export writes.
_HEADER = """#TriangulatedMeshVersion2.0
; Biosense Webster Triangulated Mesh file format, 2008

[GeneralAttributes]
NumVertex              = 4
NumTriangle            = 2
NumVertexColors        = {n_colors}

[VerticesSection]
;                   X             Y             Z        NormalX   NormalY   NormalZ  GroupID

       0 =         0.000         0.000         0.000     0.00000   0.00000   1.00000        0
       1 =         1.000         0.000         0.000     0.00000   0.00000   1.00000        0
       2 =         0.000         1.000         0.000     0.00000   0.00000   1.00000        0
       3 =         1.000         1.000         0.000     0.00000   0.00000   1.00000        0

[TrianglesSection]
;           Vertex0  Vertex1  Vertex2     NormalX   NormalY   NormalZ  GroupID

       0 =        0        1        2    0.00000   0.00000   1.00000        0
       1 =        1        3        2    0.00000   0.00000   1.00000        0

[VerticesColorsSection]
; Color Value= -10000 indicates invalid data for this coloring for this point
;{names}

"""

_ATTRIBUTES = """
[VerticesAttributesSection]
; SCAR =0: Vertex is regular vertex (not SCAR)
;   EML\tExtEML\t  SCAR
       0 =      0\t     0\t     {a}
       1 =      0\t     0\t     {b}
       2 =      0\t     0\t     0
       3 =      0\t     0\t     0
"""


def _mesh_text(names, rows, attributes=None):
    header = _HEADER.format(
        n_colors=len(names),
        names="".join(f"{n:>14s}" for n in names),
    )
    body = "\n".join(
        f"       {i} = " + " ".join(f"{v:12.5f}" for v in row) for i, row in enumerate(rows)
    )
    return header + body + "\n" + (attributes or "")


#: The 13 columns a CARTO 3 v7 export writes, in export order.
_REAL_NAMES = [
    "Unipolar",
    "Bipolar",
    "LAT",
    "Impedance",
    "A1",
    "A2",
    "A2-A1",
    "SCI",
    "ICL",
    "ACL",
    "Force",
    "Paso",
    "µBi",
]


def _rows(**columns):
    """One row per vertex, every unnamed column filled with the invalid marker."""
    rows = np.full((4, len(_REAL_NAMES)), -10000.0)
    for name, values in columns.items():
        rows[:, _REAL_NAMES.index(name)] = values
    return rows


@pytest.fixture
def mesh_file(tmp_path):
    def write(names=_REAL_NAMES, rows=None, attributes=None):
        path = tmp_path / "map.mesh"
        if rows is None:
            rows = _rows(
                Unipolar=[1.0, 2.0, 3.0, 4.0],
                Bipolar=[0.5, 1.0, 1.5, 2.0],
                LAT=[10.0, 20.0, 30.0, 40.0],
                Force=[5.0, 6.0, 7.0, 8.0],
            )
        # latin-1, as CARTO writes it — "µBi" is one byte there
        path.write_text(_mesh_text(names, rows, attributes), encoding="latin-1")
        return str(path)

    return write


def test_columns_are_keyed_by_their_declared_names(mesh_file):
    mesh = parse_carto_mesh(mesh_file())
    assert list(mesh.colors) == _REAL_NAMES
    assert np.allclose(mesh.colors["Force"], [5.0, 6.0, 7.0, 8.0])
    # the invalid marker becomes NaN rather than a plausible-looking -10000
    assert np.isnan(mesh.colors["Paso"]).all()


def test_legacy_arrays_are_filled_from_the_named_columns(mesh_file):
    mesh = parse_carto_mesh(mesh_file())
    assert np.allclose(mesh.act_bip[:, 0], [10.0, 20.0, 30.0, 40.0])  # LAT
    assert np.allclose(mesh.act_bip[:, 1], [0.5, 1.0, 1.5, 2.0])  # Bipolar
    assert np.allclose(mesh.uni_imp_frc[:, 0], [1.0, 2.0, 3.0, 4.0])  # Unipolar
    assert np.allclose(mesh.uni_imp_frc[:, 2], [5.0, 6.0, 7.0, 8.0])  # Force
    assert read_carto_mesh_file(mesh_file())[4].shape == mesh.act_bip.shape


def test_reordered_export_still_lands_in_the_right_field(mesh_file):
    """The point of reading names: a different column order must not matter."""
    names = ["LAT", "Force", "Bipolar", "Unipolar"]
    rows = np.array(
        [
            [10.0, 5.0, 0.5, 1.0],
            [20.0, 6.0, 1.0, 2.0],
            [30.0, 7.0, 1.5, 3.0],
            [40.0, 8.0, 2.0, 4.0],
        ]
    )
    mesh = parse_carto_mesh(mesh_file(names=names, rows=rows))
    assert np.allclose(mesh.act_bip[:, 0], [10.0, 20.0, 30.0, 40.0])
    assert np.allclose(mesh.act_bip[:, 1], [0.5, 1.0, 1.5, 2.0])

    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors)
    assert np.allclose(epmap.get_scalar("contact_force"), [5.0, 6.0, 7.0, 8.0])


def test_undeclared_columns_fall_back_to_positions(mesh_file):
    """A header we cannot read must not mislabel — it must stop naming."""
    rows = _rows(Unipolar=[1.0] * 4, Bipolar=[2.0] * 4, LAT=[3.0] * 4)
    mesh = parse_carto_mesh(mesh_file(names=["Unipolar", "Bipolar"], rows=rows))
    assert list(mesh.colors)[:3] == ["color_0", "color_1", "color_2"]
    assert np.allclose(mesh.act_bip[:, 0], 3.0)  # positional LAT, as before


def test_vertex_attributes_are_read(mesh_file):
    mesh = parse_carto_mesh(mesh_file(attributes=_ATTRIBUTES.format(a=1, b=1)))
    assert set(mesh.attributes) == {"EML", "ExtEML", "SCAR"}
    assert mesh.attributes["SCAR"].sum() == 2

    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors, attributes=mesh.attributes)
    assert "SCAR" in epmap.scalar_fields
    # nothing marked -> not a field: an all-zero column is not a finding
    assert "EML" not in epmap.scalar_fields


def test_empty_columns_are_not_registered(mesh_file):
    """Most of the thirteen columns are empty in any given export."""
    mesh = parse_carto_mesh(mesh_file())
    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors)

    assert set(epmap.scalar_fields) == {
        "activation_time",
        "voltage_bipolar",
        "voltage_unipolar",
        "contact_force",
    }
    assert "Impedance" not in epmap.scalar_fields


def test_micro_bipolar_is_its_own_quantity(mesh_file):
    rows = _rows(
        Unipolar=[1.0] * 4, Bipolar=[2.0] * 4, LAT=[3.0] * 4, **{"µBi": [0.25, 0.5, 0.75, 1.0]}
    )
    mesh = parse_carto_mesh(mesh_file(rows=rows))
    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors)

    micro = epmap.get_field("voltage_bipolar_micro")
    assert micro is not None and micro.unit == "mV"
    assert np.allclose(micro.values, [0.25, 0.5, 0.75, 1.0])
    # and it did not overwrite the electrode-pair bipolar voltage
    assert np.allclose(epmap.get_scalar("voltage_bipolar"), 2.0)


def test_pace_match_column_is_a_pacemap_score(mesh_file):
    """``Paso`` holds a pace-match correlation, negative-signed like the LAT slot."""
    rows = _rows(
        Unipolar=[1.0] * 4,
        Bipolar=[2.0] * 4,
        LAT=[10.0, 20.0, 30.0, 40.0],
        Paso=[-90.0, -80.0, -70.0, -60.0],
    )
    mesh = parse_carto_mesh(mesh_file(rows=rows))
    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors)

    assert np.allclose(epmap.get_scalar("pacemap_score"), [90.0, 80.0, 70.0, 60.0])
    # a real activation time alongside it keeps its own field
    assert np.allclose(epmap.get_scalar("activation_time"), [10.0, 20.0, 30.0, 40.0])


def test_a_pace_map_in_the_lat_slot_does_not_evict_paso(mesh_file):
    """Both can be present: the LAT slot's decode must not overwrite ``Paso``."""
    rows = _rows(
        Unipolar=[1.0] * 4,
        Bipolar=[2.0] * 4,
        LAT=[-99.0, -80.0, -70.0, -54.0],  # entirely negative -> a pace-match score
        Paso=[-90.0, -80.0, -70.0, -60.0],
    )
    mesh = parse_carto_mesh(mesh_file(rows=rows))
    epmap = EPMap(map_name="m", study_name="s")
    register_carto_scalars(epmap, mesh.act_bip, colors=mesh.colors)

    assert np.allclose(epmap.get_scalar("pacemap_score"), [90.0, 80.0, 70.0, 60.0])
    assert np.allclose(epmap.get_scalar("LAT"), [99.0, 80.0, 70.0, 54.0])
