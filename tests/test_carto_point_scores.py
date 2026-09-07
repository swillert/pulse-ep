"""A CARTO pace map's points carry their pace-match score, not a fake LAT.

CARTO writes the same overloaded quantity per point that it writes per
vertex: ``Map_Annotation - Reference_Annotation`` is an activation time on an
activation map and the pace-match score (negative, as in the mesh's ``LAT``
slot; ``-10000`` where the beat was not scored) on a pace map. The conversion
labelled every difference ``activation_time``, so a pace map's points carried
"activation times" of -50 … -100 ms and the reference point one of -10000 —
and the only per-site measurement of a pace map was invisible under that name.
Tags — ``Location Only`` on the reference beat, ``Scar``, a study's own labels
— are the catalogue's, resolved through its own tag table.
"""

from __future__ import annotations

import numpy as np
from lxml import etree

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.importer import fill_tags, import_carto
from pulse_ep.core.importers.carto import (
    carto_points_to_measurements,
    decode_point_annotations,
    point_primary_kind,
)
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.models import measurement_points_to_models
from pulse_ep.core.scalar_field import ACTIVATION_TIME, PACEMAP_SCORE
from pulse_ep.core.xml_proc import get_point_tags, get_tag_names


def _point(ref=2000.0, map_ann=None, **over):
    pd = {
        "point_index": 0,
        "carto_point_id": 8,
        "position_x": 1.0,
        "position_y": 2.0,
        "position_z": 3.0,
        "reference_annotation": ref,
        "map_annotation": map_ann,
        "unipolar_voltage": 2.4,
        "bipolar_voltage": 0.8,
        "cs_positions": None,
        "magnetic20_positions": None,
        "roving_positions": None,
    }
    pd.update(over)
    return pd


def _scored(*diffs, ref=2000.0):
    return [
        _point(ref=ref, map_ann=ref + d, point_index=i, carto_point_id=i + 1)
        for i, d in enumerate(diffs)
    ]


# --- decoding the annotation difference -------------------------------------


def test_a_pace_map_point_carries_its_score_not_an_activation_time():
    (p,) = carto_points_to_measurements(_scored(-97.0), primary_kind=PACEMAP_SCORE)
    assert p.get("pacemap_score") == 97.0
    assert p.measurements["pacemap_score"].kind == PACEMAP_SCORE
    assert p.measurements["pacemap_score"].unit == "%"
    assert "activation_time" not in p.measurements


def test_an_activation_map_point_keeps_its_activation_time():
    (p,) = carto_points_to_measurements(_scored(42.5), primary_kind=ACTIVATION_TIME)
    assert p.get("activation_time") == 42.5
    assert "pacemap_score" not in p.measurements


def test_the_unscored_reference_beat_has_no_value_at_all():
    """Map_Annotation -8000 against Reference 2000 is CARTO's ``-10000``: no datum."""
    (p,) = carto_points_to_measurements([_point(map_ann=-8000.0)], primary_kind=PACEMAP_SCORE)
    assert "pacemap_score" not in p.measurements
    assert "activation_time" not in p.measurements


def test_without_a_mesh_verdict_the_points_decide_by_the_mesh_rule():
    kind, values = decode_point_annotations(_scored(-97.0, -83.0, -100.0))
    assert kind == PACEMAP_SCORE and values == [97.0, 83.0, 100.0]
    kind, values = decode_point_annotations(_scored(42.5, -12.0))
    assert kind == ACTIVATION_TIME and values == [42.5, -12.0]


def test_a_sentinel_does_not_break_the_sign_rule():
    kind, values = decode_point_annotations(_scored(-10000.0, -97.0, -83.0))
    assert kind == PACEMAP_SCORE and values == [None, 97.0, 83.0]


def test_an_annotation_of_another_kind_on_a_pace_map_is_not_a_score():
    """-196 is no percentage; 30 has the wrong sign on a negatively signed map."""
    kind, values = decode_point_annotations(
        _scored(-196.0, 30.0, -97.0, -49.0), primary_kind=PACEMAP_SCORE
    )
    assert kind == PACEMAP_SCORE and values == [None, None, 97.0, 49.0]


def test_a_positively_signed_pace_map_keeps_its_scores():
    """One export writes the scores without the sign; the mesh says it is a pace map."""
    kind, values = decode_point_annotations(
        _scored(76.0, 94.0, -10000.0), primary_kind=PACEMAP_SCORE
    )
    assert kind == PACEMAP_SCORE and values == [76.0, 94.0, None]


def test_the_mesh_verdict_comes_from_the_registered_fields():
    m = EPMap("pm", "study")
    assert point_primary_kind(m) is None
    m.register_scalar("pacemap_score", np.array([80.0, 90.0]), kind=PACEMAP_SCORE)
    assert point_primary_kind(m) == PACEMAP_SCORE
    a = EPMap("lat", "study")
    a.register_scalar("activation_time", np.array([10.0, 20.0]), kind=ACTIVATION_TIME)
    assert point_primary_kind(a) == ACTIVATION_TIME


def test_a_paso_column_does_not_make_an_activation_map_a_pace_map():
    """The per-point difference belongs to the ``LAT`` slot, not to any field.

    Since colour columns are read by name, a map can carry both quantities at
    once: ``activation_time`` decoded out of a signed ``LAT`` slot, and
    ``pacemap_score`` stated by a filled ``Paso`` column beside it. Reading
    "this map has a pace-match field" as "its points are scores" turned every
    activation time on such a map into a percentage — positive ones dropped,
    negative ones reported as ``70 %``.
    """
    from pulse_ep.core.importers.carto import CARTO_SOURCE

    m = EPMap("both", "study")
    m.register_scalar(
        "pacemap_score", np.array([90.0]), kind=PACEMAP_SCORE, source=f"{CARTO_SOURCE}:Paso"
    )
    m.register_scalar(
        "activation_time",
        np.array([10.0, -20.0]),
        kind=ACTIVATION_TIME,
        source=f"{CARTO_SOURCE}:LAT",
    )

    assert point_primary_kind(m) == ACTIVATION_TIME
    kind, values = decode_point_annotations(_scored(50.0, -70.0), point_primary_kind(m))
    assert (kind, values) == (ACTIVATION_TIME, [50.0, -70.0])


def test_a_pace_match_score_in_the_lat_slot_still_wins():
    """The other direction: the slot itself decoded as a score."""
    from pulse_ep.core.importers.carto import CARTO_SOURCE

    m = EPMap("pm", "study")
    m.register_scalar(
        "pacemap_score", np.array([90.0]), kind=PACEMAP_SCORE, source=f"{CARTO_SOURCE}:LAT"
    )
    assert point_primary_kind(m) == PACEMAP_SCORE


# --- tags --------------------------------------------------------------------

_CATALOGUE = """<Study name="S">
<Maps>
  <TagsTable Count="3">
    <Tag ID="10" Short_Name="SCR" Full_Name="Scar"/>
    <Tag ID="11" Short_Name="LO" Full_Name="Location Only"/>
    <Tag ID="25" Short_Name="50-" Full_Name="50-60"/>
  </TagsTable>
  <Map Name="1-PM" FileNames="1-PM.mesh">
    <CartoPoints Count="5">
      <Point Id="1" Position3D="0 0 0"><Tags Count="1">11</Tags></Point>
      <Point Id="8" Position3D="1 0 0"/>
      <Point Id="9" Position3D="0 1 0"><Tags Count="2">10 99</Tags></Point>
      <Point Id="10" Position3D="0.5 0.5 0"/>
      <Point Id="11" Position3D="0.2 0.2 0"><Tags Count="0"/></Point>
    </CartoPoints>
  </Map>
</Maps>
</Study>"""


def test_tags_are_read_from_the_catalogue_and_named_by_its_table():
    tree = etree.ElementTree(etree.fromstring(_CATALOGUE))
    names = get_tag_names(tree)
    assert names == {10: "Scar", 11: "Location Only", 25: "50-60"}
    tags = get_point_tags(tree.find(".//Maps/Map"))
    assert tags == [[11], [], [10, 99], [], []]
    dicts = [_point(point_index=i) for i in range(5)]
    fill_tags(dicts, tags, names)
    assert [d["tags"] for d in dicts] == [["Location Only"], [], ["Scar", "99"], [], []]


def test_tags_travel_to_the_measurement_point_and_through_the_orm():
    (p,) = carto_points_to_measurements([_point(map_ann=1903.0, tags=["Location Only"])])
    assert p.tags == ["Location Only"]
    (row,) = measurement_points_to_models([p], map_id=3)
    assert row.tags == ["Location Only"]
    assert row.to_measurement_point().tags == ["Location Only"]


def test_a_point_without_tags_is_serialised_with_an_empty_list():
    p = MeasurementPoint(position=np.zeros(3))
    (row,) = measurement_points_to_models([p], map_id=3)
    assert row.tags == []
    assert row.to_measurement_point().tags == []


# --- end to end on a minimal export -----------------------------------------

_MESH = """#TriangulatedMeshVersion2.0

[GeneralAttributes]
NumVertex              = 4
NumTriangle            = 2
NumVertexColors        = 3

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
;      Unipolar       Bipolar           LAT

       0 =      1.00000      0.50000    -90.00000
       1 =      2.00000      1.00000    -80.00000
       2 =      3.00000      1.50000    -70.00000
       3 =      4.00000      2.00000    -60.00000
"""

_POINT_XML = """<Point ID="{pid}" Date="04/11/24" Time="10:52:04">
    <Annotations StartTime="7867689" Reference_Annotation="2000" Map_Annotation="{map_ann}" />
    <WOI From="13" To="100" />
    <Voltages Unipolar="3.363" Bipolar="4.155" />
</Point>"""


def _write_export(tmp_path):
    d = tmp_path / "Export" / "Pat" / "Visit" / "Study"
    d.mkdir(parents=True)
    (d / "Study.xml").write_text(_CATALOGUE, encoding="utf-8")
    (d / "1-PM.mesh").write_text(_MESH, encoding="latin-1")
    scored = ((1, -8000), (8, 1903), (9, 1917), (10, 1804), (11, 1950))
    (d / "1-PM_Points_Export.xml").write_text(
        '<Points Map_Name="1-PM">'
        + "".join(
            f'<Point ID="{pid}" File_Name="1-PM_P{pid}_Point_Export.xml"/>' for pid, _ in scored
        )
        + "</Points>",
        encoding="utf-8",
    )
    for pid, map_ann in scored:
        (d / f"1-PM_P{pid}_Point_Export.xml").write_text(
            _POINT_XML.format(pid=pid, map_ann=map_ann), encoding="utf-8"
        )
    return d / "Study.xml"


def test_a_pace_map_import_yields_scores_and_tags(tmp_path):
    study = import_carto(str(_write_export(tmp_path)))
    assert study is not None and len(study.epmaps) == 1
    (epmap,) = study.epmaps
    assert epmap.field_of_kind(PACEMAP_SCORE) is not None  # the mesh's LAT slot is all negative
    points = {p.source_id: p for p in epmap.measurement_points}
    assert set(points) == {"1", "8", "9", "10", "11"}
    assert points["1"].tags == ["Location Only"]
    assert "pacemap_score" not in points["1"].measurements  # the unscored reference beat
    assert points["8"].get("pacemap_score") == 97.0
    assert points["9"].get("pacemap_score") == 83.0
    assert points["10"].get("pacemap_score") is None  # -196: not a percentage
    assert points["11"].get("pacemap_score") == 50.0
    assert points["9"].tags == ["Scar", "99"] and points["11"].tags == []
    assert all("activation_time" not in p.measurements for p in points.values())
    np.testing.assert_allclose(points["8"].position, [1.0, 0.0, 0.0])
