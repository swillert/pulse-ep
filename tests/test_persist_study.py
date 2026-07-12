"""persist_study orchestration — verified against a fake session (no live DB).

The real Postgres round-trip (JSONB/ARRAY) is exercised manually; here we
check that persist_study builds the right rows in the right order.
"""

from __future__ import annotations

import numpy as np

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.models import (
    EPMapAttributes,
    EPMapModel,
    MeasurementPointModel,
    StudyModel,
    persist_study,
)
from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR
from pulse_ep.core.study import Study


class FakeSession:
    """Minimal session: records add()s and assigns ids on flush()."""

    def __init__(self):
        self.added = []
        self._id = 0
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._id += 1
                obj.id = self._id

    def commit(self):
        self.commits += 1


def _study():
    verts = np.zeros((3, 3))
    tris = np.array([[0, 1, 2]])
    ep = EPMap(map_name="m", study_name="s", vertices=verts, triangles=tris)
    ep.register_scalar("voltage_bipolar", np.array([0.5, 1.0, 1.5]), kind=VOLTAGE_BIPOLAR)
    ep.measurement_points = [
        MeasurementPoint(position=np.array([1.0, 2.0, 3.0]), source_id="7"),
    ]
    return Study("guid-123", ep, vendor="ensite", provenance={"software_version": "6.0"})


def test_persist_builds_study_maps_and_points():
    session = FakeSession()
    study_model = persist_study(session, _study())

    kinds = [type(o) for o in session.added]
    assert StudyModel in kinds and EPMapModel in kinds
    assert EPMapAttributes in kinds and MeasurementPointModel in kinds

    sm = next(o for o in session.added if isinstance(o, StudyModel))
    assert sm.vendor == "ensite" and sm.name == "guid-123"

    em = next(o for o in session.added if isinstance(o, EPMapModel))
    assert em.study_id == sm.id  # FK wired via flush-assigned id
    assert em.scalar_fields["voltage_bipolar"]["kind"] == "voltage_bipolar"

    mp = next(o for o in session.added if isinstance(o, MeasurementPointModel))
    assert mp.map_id == em.id
    assert mp.position == [1.0, 2.0, 3.0]

    assert study_model is sm
    assert session.commits >= 1
