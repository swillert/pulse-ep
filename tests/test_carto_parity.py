"""CARTO reaching the same shape as EnSiteX: points, plan, commit.

CARTO's per-point data was always parsed, but stopped at the fixed-column
legacy table, and the importer had no ``prepare``/``commit`` at all — so a
CARTO bundle could not be reviewed, and its points could not be compared with
an EnSiteX point set. These tests pin the parity.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.carto import CartoImporter, carto_points_to_measurements
from pulse_ep.core.importers.source import DirSource
from pulse_ep.core.scalar_field import ACTIVATION_TIME, VOLTAGE_BIPOLAR, VOLTAGE_UNIPOLAR

_STUDY_XML = (
    '<Study name="TestStudy"><Maps>'
    '<Map Name="1-LA" FileNames="1-LA.mesh"><CartoPoints Count="120"/></Map>'
    '<Map Name="2-PaceMap" FileNames="2-PaceMap.mesh"><CartoPoints Count="45"/></Map>'
    '<Map Name="3-Tiny" FileNames="3-Tiny.mesh"><CartoPoints Count="2"/></Map>'
    "</Maps></Study>"
)


def _point(**over):
    pd = {
        "point_index": 0,
        "carto_point_id": 37,
        "position_x": 1.0,
        "position_y": 2.0,
        "position_z": 3.0,
        "reference_annotation": 100.0,
        "map_annotation": 142.5,
        "unipolar_voltage": 2.4,
        "bipolar_voltage": 0.8,
        "cs_positions": None,
        "magnetic20_positions": None,
        "roving_positions": None,
    }
    pd.update(over)
    return pd


# --- per-point conversion --------------------------------------------------


def test_points_carry_the_same_quantities_ensite_does():
    p = carto_points_to_measurements([_point()])[0]
    assert p.get("voltage_bipolar") == 0.8
    assert p.get("voltage_unipolar") == 2.4
    np.testing.assert_allclose(p.position, [1.0, 2.0, 3.0])
    assert p.source_id == "37"
    assert p.measurements["voltage_bipolar"].kind == VOLTAGE_BIPOLAR
    assert p.measurements["voltage_unipolar"].kind == VOLTAGE_UNIPOLAR


def test_activation_time_follows_cartos_annotation_convention():
    """LAT = Map_Annotation - Reference_Annotation."""
    p = carto_points_to_measurements([_point()])[0]
    assert p.get("activation_time") == 42.5
    assert p.measurements["activation_time"].kind == ACTIVATION_TIME
    assert p.measurements["activation_time"].unit == "ms"


def test_activation_time_needs_both_annotations():
    p = carto_points_to_measurements([_point(reference_annotation=None)])[0]
    assert "activation_time" not in p.measurements


def test_catheter_positions_become_labelled_electrodes():
    p = carto_points_to_measurements(
        [_point(cs_positions=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0], roving_positions=[5.0, 5.0, 5.0])]
    )[0]
    assert set(p.electrodes) == {"CS_1", "CS_2", "ROV_1"}
    np.testing.assert_allclose(p.electrodes["CS_2"], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(p.electrodes["ROV_1"], [5.0, 5.0, 5.0])


def test_a_point_without_a_position_is_skipped():
    assert carto_points_to_measurements([_point(position_x=None)]) == []


def test_a_trailing_partial_electrode_triple_is_ignored():
    p = carto_points_to_measurements([_point(cs_positions=[0.0, 0.0, 0.0, 9.0])])[0]
    assert set(p.electrodes) == {"CS_1"}


def test_missing_voltages_are_omitted_not_zeroed():
    p = carto_points_to_measurements([_point(bipolar_voltage=None, unipolar_voltage=None)])[0]
    assert "voltage_bipolar" not in p.measurements
    assert "voltage_unipolar" not in p.measurements


# --- prepare / commit ------------------------------------------------------


def _study_dir(tmp_path):
    d = tmp_path / "a" / "b" / "c" / "StudyDir"
    d.mkdir(parents=True, exist_ok=True)
    (d / "Study.xml").write_text(_STUDY_XML)
    return d


def test_prepare_lists_maps_without_touching_a_mesh(tmp_path):
    plan = CartoImporter().prepare(DirSource(_study_dir(tmp_path)))
    assert len(plan.studies) == 1
    sp = plan.studies[0]
    assert sp.vendor == "carto"
    assert [m.map_name for m in sp.maps] == ["1-LA", "2-PaceMap", "3-Tiny"]
    # no mesh file exists at all — prepare must not have needed one
    assert sp.maps[0].files == ["1-LA.mesh"]


def test_prepare_excludes_maps_below_the_point_threshold(tmp_path):
    plan = CartoImporter().prepare(DirSource(_study_dir(tmp_path)))
    tiny = next(m for m in plan.studies[0].maps if m.map_name == "3-Tiny")
    assert tiny.include is False and tiny.issues


def test_prepare_study_name_matches_what_commit_produces(tmp_path):
    """The queue's duplicate check compares these, so they must agree."""
    from pulse_ep.core.importer import extract_subfolder

    d = _study_dir(tmp_path)
    plan = CartoImporter().prepare(DirSource(d))
    expected = f"{extract_subfolder(str(d / 'Study.xml'), 4)}-TestStudy"
    assert plan.studies[0].study_name == expected


def test_commit_only_imports_the_maps_the_reviewer_kept(tmp_path, monkeypatch):
    seen = {}

    def fake_import_studies(xmls, map_filter=None):
        seen["filter"] = map_filter
        return []

    import pulse_ep.core.importer as legacy

    monkeypatch.setattr(legacy, "import_studies", fake_import_studies)

    imp = CartoImporter()
    source = DirSource(_study_dir(tmp_path))
    plan = imp.prepare(source)
    for m in plan.studies[0].maps:
        m.include = m.map_name == "2-PaceMap"
    imp.commit(plan, source)

    assert seen["filter"] == "^(?:2\\-PaceMap)$"


def test_parse_no_longer_dies_on_a_missing_filter(tmp_path):
    """``import_carto(filter=None)`` used to raise unconditionally, which made
    every registry-driven CARTO import — and the whole queue path — fail."""
    studies = CartoImporter().parse(DirSource(_study_dir(tmp_path)))
    assert isinstance(studies, list)
