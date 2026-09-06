"""Import an Abbott EnSiteX export into the pulse-ep database.

Runs the prepare -> commit -> persist pipeline for an export folder or ZIP:

    pulse-ep-import-ensite --input /path/to/export            # folder or .zip
    pulse-ep-import-ensite --input ... --dry-run              # show the plan only
    pulse-ep-import-ensite --input ... --clear                # reimport if present
    pulse-ep-import-ensite --input ... --waveforms --store-dir /var/pulse/waveforms

Idempotent by study identity (the export GUID): an already-imported study is
skipped unless ``--clear`` is given.
"""

from __future__ import annotations

import argparse

from pulse_ep.core.importers.ensite import EnsiteImporter
from pulse_ep.core.importers.plan import ImportPlan
from pulse_ep.core.importers.source import source_for


def _print_plan(plan: ImportPlan) -> None:
    for sp in plan.studies:
        print(f"study {sp.study_name}  (vendor={sp.vendor})")
        for m in sp.maps:
            issues = f"  issues={m.issues}" if m.issues else ""
            print(
                f"  map {m.map_name}  verts={m.n_vertices}  "
                f"fields={list(m.scalar_fields)}  point-files={len(m.points_files)}{issues}"
            )
        wf = sp.waveforms
        print(
            f"  waveforms: {len(wf.files)} files ~{wf.estimated_bytes / 1e6:.1f} MB "
            f"(include={wf.include})"
        )
    # Plan-level issues say what an export cannot deliver — an export with no
    # geometry, say. Printing only per-map issues hid exactly the case where
    # there are no maps to hang them on.
    for issue in plan.issues:
        print(f"  ! {issue}")


def _delete_study(session, study_model) -> None:
    """Remove a study and its maps / attributes / measurement points."""
    from pulse_ep.core.models import (
        EPMapAttributes,
        EPMapModel,
        MeasurementPointModel,
        PlacedPointModel,
    )

    map_ids = [e.id for e in session.query(EPMapModel).filter_by(study_id=study_model.id).all()]
    if map_ids:
        session.query(MeasurementPointModel).filter(
            MeasurementPointModel.map_id.in_(map_ids)
        ).delete(synchronize_session=False)
        session.query(EPMapAttributes).filter(EPMapAttributes.map_id.in_(map_ids)).delete(
            synchronize_session=False
        )
        session.query(EPMapModel).filter(EPMapModel.id.in_(map_ids)).delete(
            synchronize_session=False
        )
    session.query(PlacedPointModel).filter_by(study_id=study_model.id).delete(
        synchronize_session=False
    )
    session.delete(study_model)
    session.commit()


def import_ensite(
    path: str,
    clear: bool = False,
    waveforms: bool = False,
    store_dir: str | None = None,
    dry_run: bool = False,
) -> list[int]:
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import StudyModel, ingest_waveforms, persist_study
    from pulse_ep.core.waveform import FilesystemStore

    source = source_for(path)
    importer = EnsiteImporter()
    plan = importer.prepare(source)
    if waveforms:
        for sp in plan.studies:
            sp.waveforms.include = True

    _print_plan(plan)
    if dry_run:
        print("dry-run: nothing written")
        return []

    studies = importer.commit(plan, source)
    store = FilesystemStore(store_dir) if (waveforms and store_dir) else None

    imported: list[int] = []
    with get_db_session() as session:
        for study, sp in zip(studies, plan.studies):  # noqa: B905
            existing = StudyModel.find_by_name(study.name, session)
            if existing is not None:
                if not clear:
                    print(f"skip existing study {study.name} (use --clear to reimport)")
                    continue
                _delete_study(session, existing)

            study_model = persist_study(session, study)
            n_points = sum(len(getattr(e, "measurement_points", None) or []) for e in study.epmaps)
            print(f"imported {study.name}: {len(study.epmaps)} maps, {n_points} points")

            if store is not None and sp.waveforms.include:
                rows = ingest_waveforms(
                    ImportPlan(studies=[sp]), source, store, study_id=study_model.id
                )
                for row in rows:
                    session.add(row)
                session.commit()
                print(f"  + {len(rows)} waveforms -> {store_dir}")

            imported.append(study_model.id)
    return imported


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-import-ensite", description="Import an Abbott EnSiteX export."
    )
    p.add_argument("--input", "-i", required=True, help="Path to an export folder or ZIP.")
    p.add_argument("--clear", action="store_true", help="Reimport if the study already exists.")
    p.add_argument("--waveforms", action="store_true", help="Also import waveforms (opt-in).")
    p.add_argument("--store-dir", help="WaveformStore root directory (used with --waveforms).")
    p.add_argument("--dry-run", action="store_true", help="Show the import plan; write nothing.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    import_ensite(
        args.input,
        clear=args.clear,
        waveforms=args.waveforms,
        store_dir=args.store_dir,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
