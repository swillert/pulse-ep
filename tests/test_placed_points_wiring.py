"""PlacedPoint ORM serialisation + prepare/commit wiring + persist."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import EnsiteImporter
from pulse_ep.core.importers.source import DirSource
from pulse_ep.core.models import placed_points_to_models
from pulse_ep.core.placed_point import MARKER, PlacedPoint

_LESIONS = (
    "Export Data Element: Lesions\n"
    "Text,Type,Surface,x,y,z,xt,yt,zt,xw,yw,zw,Proj Distance,Display,Visible,R,G,B,Diameter,Timestamp,Annotation\n"
    "L1,3DE,[N/A],-17.2,-105.7,42.3,-17.2,-105.7,42.3,-17.2,-105.7,42.3,1.88,1,1,1,1,0,5.0,13:16:37,note\n"
)


def test_placed_point_model_roundtrip():
    p = PlacedPoint(
        type=MARKER, position=np.array([1.0, 2.0, 3.0]), label="x", attributes={"power": 25.0}
    )
    (model,) = placed_points_to_models([p], study_id=9)
    assert model.study_id == 9 and model.type == MARKER
    assert model.position == [1.0, 2.0, 3.0]
    assert model.attributes == {"power": 25.0}

    back = model.to_placed_point()
    assert back.type == MARKER and back.label == "x"
    np.testing.assert_array_equal(back.position, [1.0, 2.0, 3.0])


def test_prepare_and_commit_attach_placed_points(tmp_path):
    (tmp_path / "Lesions.csv").write_text(_LESIONS)
    (tmp_path / "AutoMark_Data.csv").write_text(
        "Exported from Software Version: 6.0\nExport from Study: s-1\n"
    )
    src = DirSource(tmp_path)
    imp = EnsiteImporter()

    plan = imp.prepare(src)
    files = plan.studies[0].placed_point_files
    assert any("Lesions.csv" in f for f in files)

    study = imp.commit(plan, src)[0]
    markers = [p for p in study.placed_points if p.type == MARKER]
    assert len(markers) == 1
    assert markers[0].attributes["marker_type"] == "3DE"


def test_opt_out_of_placed_points(tmp_path):
    (tmp_path / "Lesions.csv").write_text(_LESIONS)
    src = DirSource(tmp_path)
    imp = EnsiteImporter()
    plan = imp.prepare(src)
    plan.studies[0].include_placed_points = False
    assert imp.commit(plan, src)[0].placed_points == []
