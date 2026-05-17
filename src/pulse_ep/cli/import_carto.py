#!/usr/bin/env python3
"""
pulse-ep-import-carto — Import CARTO studies into the pulse-ep database.

CSV-free, filesystem-driven replacement for the legacy
``import_studies.py`` script. Study XML files are discovered via
:func:`pulse_ep.core.importer.discover_carto_exports` rather than a
hard-coded CSV path list, eliminating the historical risk of
patient-identifiable filenames leaking into source control.

Typical usage
-------------

Incremental import from a directory of studies::

    pulse-ep-import-carto --input /data/cartoexports

Dry-run (discover files, do not write to DB)::

    pulse-ep-import-carto --input /data/cartoexports --dry-run

Wipe the DB and reimport::

    pulse-ep-import-carto --input /data/cartoexports --clear

Filter map names::

    pulse-ep-import-carto --input /data/cartoexports \\
        --map-filter "PaceMap|LAT|BiAtrial"

Compact progress line::

    pulse-ep-import-carto --input /data/cartoexports --progress
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time

from pulse_ep.core import mesh_proc, xml_proc
from pulse_ep.core.importer import discover_carto_exports, extract_subfolder
from pulse_ep.core.point_importer import import_map_points

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger("pulse_ep.cli.import_carto")


# ── Progress tracking (module-level state) ────────────────────────────────
_progress = {
    "enabled": False,
    "start_time": 0.0,
    "total_studies": 0,
    "done_studies": 0,
    "done_maps": 0,
    "done_points": 0,
    "failed_maps": 0,
}


def _print_progress(force_nl: bool = False) -> None:
    """Render a single compact progress line."""
    p = _progress
    elapsed = time.time() - p["start_time"]
    mm, ss = divmod(int(elapsed), 60)
    pct = (p["done_studies"] / p["total_studies"] * 100) if p["total_studies"] else 0
    line = (
        f"\r  {p['done_studies']}/{p['total_studies']} studies  "
        f"{p['done_maps']} maps  {p['done_points']} pts  "
        f"{p['failed_maps']} failed  "
        f"[{pct:3.0f}%  {mm}:{ss:02d}]"
    )
    end = "\n" if force_nl else ""
    print(line, end=end, flush=True)


# ── Per-study import ─────────────────────────────────────────────────────
def _import_single_study(file_path: str, map_filter: str, dry_run: bool) -> None:
    """
    Import one CARTO study (maps + points) into the DB.

    Parameters
    ----------
    file_path : str
        Absolute path to the CARTO study XML file.
    map_filter : str
        Case-insensitive regex for filtering map names.
    dry_run : bool
        If True, discover and parse but do not write to DB.
    """
    # DB imports happen here so that --dry-run does not require DB config.
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import (
        EPMapAttributes,
        EPMapModel,
        EPMapPoint,
        StudyModel,
    )

    progress = _progress["enabled"]

    if os.path.basename(file_path).startswith("._"):
        return

    try:
        xml_tree = xml_proc.process_xml(file_path)
        study_name_raw = xml_proc.get_study_name(xml_tree)
    except Exception as e:
        log.warning(f"Failed to load XML {file_path}: {e}")
        return

    study_dir = os.path.dirname(file_path)
    study_name = f"{extract_subfolder(file_path, 4)}-{study_name_raw}"

    nMaps, names, numPtsPerMap, filenames = xml_proc.get_maps(xml_tree)
    if nMaps == 0:
        if not progress:
            log.info(f"No maps in {file_path}, skipping.")
        return

    map_indices = [
        i
        for i, (name, npts) in enumerate(zip(names, numPtsPerMap))  # noqa: B905
        if re.search(map_filter, name, re.IGNORECASE) and npts >= 5
    ]

    if not map_indices:
        if not progress:
            log.info(f"No maps after filter in {file_path}, skipping.")
        return

    if not progress:
        log.info(f"Study '{study_name}': {len(map_indices)} map(s) to import")

    if dry_run:
        for mi in map_indices:
            log.info(f"  [dry-run] would import: {names[mi]} ({numPtsPerMap[mi]} pts)")
        _progress["done_studies"] += 1
        if progress:
            _print_progress()
        return

    with get_db_session() as session:
        study_model = StudyModel.find_by_name(study_name, session)
        if study_model is None:
            study_model = StudyModel(name=study_name)
            study_model.create(session)
            session.flush()

        for map_index in map_indices:
            map_name = names[map_index]

            existing = (
                session.query(EPMapModel)
                .filter_by(study_id=study_model.id, map_name=map_name)
                .first()
            )
            if existing:
                if not progress:
                    log.info(f"  Already exists: {map_name}")
                continue

            try:
                mesh_file = filenames[map_index]
                mesh_path = os.path.join(study_dir, mesh_file)
                (
                    triangles,
                    vertices,
                    triangle_areas,
                    is_vertex_at_edge,
                    act_bip,
                    normals,
                    uni_imp_frc,
                ) = mesh_proc.read_carto_mesh_file(mesh_path)

                map_element = xml_proc.get_map_element(xml_tree, map_index)
                xyz_from_xml = xml_proc.get_xyz(map_element)

                epmap_model = EPMapModel(
                    map_name=map_name,
                    study_id=study_model.id,
                    study_name=study_name,
                    number_of_points=numPtsPerMap[map_index],
                    mesh_file=mesh_file,
                    triangles=triangles.tolist(),
                    vertices=vertices.tolist(),
                    triangle_areas=triangle_areas.tolist(),
                    is_vertex_at_edge=is_vertex_at_edge.tolist(),
                    act_bip=act_bip.tolist(),
                    normals=normals.tolist(),
                    uni_imp_frc=(uni_imp_frc.tolist() if uni_imp_frc is not None else None),
                )
                session.add(epmap_model)
                session.flush()

                point_dicts, _ref_count = import_map_points(study_dir, map_name)

                for i, pd in enumerate(point_dicts):
                    if (
                        pd["position_x"] is None
                        and xyz_from_xml is not None
                        and i < len(xyz_from_xml)
                    ):
                        pd["position_x"] = float(xyz_from_xml[i, 0])
                        pd["position_y"] = float(xyz_from_xml[i, 1])
                        pd["position_z"] = float(xyz_from_xml[i, 2])

                for pd in point_dicts:
                    pt = EPMapPoint(map_id=epmap_model.id, **pd)
                    session.add(pt)

                session.add(EPMapAttributes(map_id=epmap_model.id, attributes={}))

                _t0 = time.time()
                session.commit()
                _dt = time.time() - _t0
                n_pts = len(point_dicts)

                _progress["done_maps"] += 1
                _progress["done_points"] += n_pts

                if progress:
                    _print_progress()
                else:
                    log.info(f"  ✓ {map_name} ({n_pts} pts, commit={_dt:.1f}s)")

            except Exception as e:
                _progress["failed_maps"] += 1
                if progress:
                    _print_progress()
                else:
                    log.warning(f"  Failed map '{map_name}': {e}")
                session.rollback()
                continue

    _progress["done_studies"] += 1
    if progress:
        _print_progress()


# ── DB wipe helper ───────────────────────────────────────────────────────
def _wipe_database(progress: bool) -> None:
    """Drop and recreate all pulse-ep tables, then reseed metadata."""
    from sqlalchemy import text

    from pulse_ep.core.database import (
        create_db_engine,
        get_db_session,
        seed_attribute_metadata,
    )
    from pulse_ep.core.models import Base

    engine = create_db_engine()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for tbl in [
            "ep_map_points",
            "epmap_attributes",
            "reports",
            "epmaps",
            "studies",
            "attribute_metadata",
            "colormaps",
            "users",
        ]:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
    if not progress:
        log.info("Dropped all tables.")
    Base.metadata.create_all(engine)
    if not progress:
        log.info("Recreated tables.")
    with get_db_session() as session:
        seed_attribute_metadata(session)


# ── CLI entry point ──────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-import-carto",
        description=(
            "Import CARTO studies (XML + mesh + points) into the pulse-ep "
            "database. Discovers study XML files from a directory tree, "
            "replacing the legacy CSV-driven flow."
        ),
    )
    p.add_argument(
        "--input",
        "-i",
        required=True,
        metavar="DIR",
        help="Root directory containing CARTO study XML files.",
    )
    p.add_argument(
        "--pattern",
        default="*.xml",
        metavar="GLOB",
        help="Glob pattern for study XML files (default: %(default)s).",
    )
    p.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into subdirectories.",
    )
    p.add_argument(
        "--map-filter",
        default=".*",
        metavar="REGEX",
        help=("Case-insensitive regex for filtering map names (default: %(default)s — match all)."),
    )
    p.add_argument(
        "--clear",
        action="store_true",
        help="Drop and recreate all tables before importing.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and parse, but do not write to the database.",
    )
    p.add_argument(
        "--progress",
        action="store_true",
        help="Compact one-line progress display.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.progress:
        _progress["enabled"] = True
        logging.getLogger("pulse_ep.core.point_importer").setLevel(logging.WARNING)
        log.setLevel(logging.WARNING)

    try:
        files = discover_carto_exports(
            args.input,
            pattern=args.pattern,
            recursive=not args.no_recursive,
        )
    except FileNotFoundError as e:
        log.error(str(e))
        return 2

    if not files:
        log.error(f"No CARTO study files matched {args.pattern!r} under {args.input!r}.")
        return 3

    if args.clear:
        if args.dry_run:
            log.info("[dry-run] would wipe database.")
        else:
            _wipe_database(progress=args.progress)

    if args.progress:
        _progress["total_studies"] = len(files)
        _progress["start_time"] = time.time()
        print(f"  Importing {len(files)} studies...")
        _print_progress()
    else:
        log.info(f"Found {len(files)} study file(s) to process.")

    for fp in files:
        _import_single_study(fp, args.map_filter, args.dry_run)

    if args.progress:
        _print_progress(force_nl=True)
        p = _progress
        elapsed = time.time() - p["start_time"]
        mm, ss = divmod(int(elapsed), 60)
        print(
            f"  Done. {p['done_maps']} maps, {p['done_points']} points "
            f"in {mm}:{ss:02d} ({p['failed_maps']} failed)"
        )
    else:
        log.info("Import complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
