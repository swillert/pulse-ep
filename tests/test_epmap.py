"""Domain-object tests for :class:`pulse_ep.EPMap`."""

from __future__ import annotations

import numpy as np
import pytest

from pulse_ep import EPMap, Study


def test_epmap_requires_name() -> None:
    with pytest.raises(ValueError, match="map_name"):
        EPMap(map_name=None, study_name="X")


def test_epmap_holds_array_references(synthetic_atrium_arrays) -> None:
    vertices, triangles, scores = synthetic_atrium_arrays
    epmap = EPMap(
        map_name="m1",
        study_name="s1",
        vertices=vertices,
        triangles=triangles,
        act_bip=np.column_stack([scores, np.zeros_like(scores)]),
    )
    assert epmap.map_name == "m1"
    assert epmap.study_name == "s1"
    assert epmap.vertices is vertices
    assert epmap.triangles is triangles


def test_study_aggregates_epmaps() -> None:
    e1 = EPMap(map_name="m1", study_name="s")
    e2 = EPMap(map_name="m2", study_name="s")
    study = Study("s", [e1, e2])
    assert study.name == "s"
    assert study.epmaps == [e1, e2]


def test_study_accepts_single_epmap() -> None:
    e1 = EPMap(map_name="m1", study_name="s")
    study = Study("s", e1)
    assert study.epmaps == [e1]
