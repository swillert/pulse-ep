"""Write a stored map as an OpenEP ``userdata`` MATLAB file.

    pulse-ep-export-openep --map-id 12 -o map12.mat

The point is not the file format. OpenEP parses CARTO and Precision itself;
what it cannot read is EnSite X, and pulse-ep can. A map from either vendor
becomes one structure, so any OpenEP analysis runs on both.

Load it in MATLAB with ``examples/matlab/pe_to_openep.m``, which rebuilds the
``triangulation`` object a ``.mat`` cannot carry — and prints the notes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse-ep-export-openep", description=__doc__)
    parser.add_argument("--map-id", type=int, required=True, help="EPMap id in the database.")
    parser.add_argument("-o", "--output", help="Target .mat (default: map<id>.mat).")
    parser.add_argument(
        "--no-points",
        action="store_true",
        help="Omit measurement points — geometry and per-vertex scalars only.",
    )
    args = parser.parse_args(argv)

    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import EPMapModel, StudyModel
    from pulse_ep.core.openep import write_userdata

    out = Path(args.output or f"map{args.map_id}.mat")
    with get_db_session() as session:
        model = session.get(EPMapModel, args.map_id)
        if model is None:
            print(f"no map with id {args.map_id}", file=sys.stderr)
            return 2
        epmap = model.to_epmap(include_points=not args.no_points)
        study = session.get(StudyModel, model.study_id) if model.study_id else None
        notes = write_userdata(epmap, out, study_name=getattr(study, "name", None))

    print(f"wrote {out} — map {epmap.map_name!r}")
    # Printed, not buried in the file: a reader who does not open MATLAB should
    # still learn what the structure could not carry.
    for note in notes[1:]:
        print(f"  note: {note}")
    if not notes[1:]:
        print("  every slot OpenEP has was filled")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
