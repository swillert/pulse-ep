"""Populate an explicitly selected, empty test database with public controls."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np


def main():
    if os.environ.get("PULSE_EP_TEST_DATABASE") != "1":
        raise RuntimeError("Set PULSE_EP_TEST_DATABASE=1 for a disposable test database")
    target = Path(os.environ["PULSE_EP_TEST_CONFIG"])
    from flask_jwt_extended import create_access_token

    from pulse_ep import EPMap
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.importers.carto import CartoImporter
    from pulse_ep.core.importers.ensite import EnsiteImporter
    from pulse_ep.core.importers.source import DirSource
    from pulse_ep.core.measurement import MeasurementPoint
    from pulse_ep.core.models import EPMapModel, StudyModel, persist_study, waveform_row
    from pulse_ep.core.placed_point import ABLATION, PlacedPoint
    from pulse_ep.core.study import Study
    from pulse_ep.core.waveform import FilesystemStore, Waveform
    from pulse_ep.server.app import app

    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
    cfg = {}
    with get_db_session() as session:
        if session.query(StudyModel).count():
            raise RuntimeError("Test seed requires an empty database; no records were changed")
        empty = persist_study(session, Study("Empty control", vendor=None))
        cfg["empty_study"] = empty.id
        for vendor, importer in [("carto", CartoImporter()), ("ensite", EnsiteImporter())]:
            source = DirSource(fixtures / vendor / "synthetic_study")
            study = importer.commit(importer.prepare(source), source)[0]
            # Give controls distinct identities even if fixtures share a name.
            study.name = f"MATLAB {vendor} control"
            for epmap in study.epmaps:
                epmap.study_name = study.name
            stored = persist_study(session, study)
            model = session.query(EPMapModel).filter_by(study_id=stored.id).one()
            cfg[vendor] = {"study": stored.id, "map": model.id}
        point = MeasurementPoint(
            np.array([0.0, 1.0, 2.0]),
            source_id="p1",
            index=0,
            annotations={"reference": 2, "map": 3, "woi_from": -1, "woi_to": 2},
            electrodes={"BIP": np.array([0.0, 1.0, 2.0])},
        )
        point.add("lat", 1.0, "activation_time", "ms")
        epmap = EPMap("Point-only control", "Signal control", measurement_points=[point])
        study = Study(
            "Signal control",
            [epmap],
            vendor="carto",
            placed_points=[PlacedPoint(type=ABLATION, position=np.array([0.0, 1.0, 2.0]))],
        )
        stored = persist_study(session, study)
        model = session.query(EPMapModel).filter_by(study_id=stored.id).one()
        wave = Waveform(
            data=np.array([[1.0, 10], [2, 20], [3, 30], [4, 40]]),
            channels=["BIP", "V1"],
            units=["mV", "mV"],
            sample_rate=1000,
            signal_type="ecg",
            time=np.arange(4) / 1000,
            meta={
                "map_name": epmap.map_name,
                "start_time": 0,
                "points": [{"point_id": "p1", "mapping_channels": {"bipolar": "BIP"}}],
            },
        )
        store = FilesystemStore(os.environ["PULSE_EP_WAVEFORM_STORE_DIR"])
        uri = store.write(wave, "matlab-public-control")
        row = waveform_row(wave, uri, study_id=stored.id, map_id=model.id, point_source_id="p1")
        session.add(row)
        session.commit()
        cfg["signal"] = {"study": stored.id, "map": model.id, "waveform": row.id}
    with app.app_context():
        cfg["expired_token"] = create_access_token(
            identity="matlab-control", expires_delta=timedelta(seconds=-10)
        )
    target.write_text(json.dumps(cfg, indent=2))
    target.chmod(0o600)
    print("Synthetic MATLAB controls imported")


if __name__ == "__main__":
    main()
