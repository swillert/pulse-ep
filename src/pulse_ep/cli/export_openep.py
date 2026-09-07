"""Write a stored map as an OpenEP ``userdata`` MATLAB file.

    pulse-ep-export-openep --map-id 12 -o map12.mat

Maps from either vendor become a structure for OpenEP analyses supported by
the available quantities. MATLAB can load the file with ``load`` and rebuild
``surface.triRep`` with ``triangulation(Triangulation, X)``. For direct REST
access, use ``examples/matlab/pe_to_openep.m`` instead.
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
        "--include-signals",
        action="store_true",
        help="Include stored point-linked electrograms and ECG.",
    )
    parser.add_argument(
        "--ecg-channels", help="Comma-separated ECG leads (default: available standard leads)."
    )
    parser.add_argument(
        "--signal-scale-to-mv",
        type=float,
        help="Explicit calibration for channels whose stored unit is unknown.",
    )
    ablation = parser.add_mutually_exclusive_group()
    ablation.add_argument(
        "--ablation-scope",
        choices=["none", "study"],
        default="none",
        help="Explicitly associate this study's RF markers with the selected map.",
    )
    ablation.add_argument(
        "--ablation-ids", help="Comma-separated placed-point database IDs from this study."
    )
    parser.add_argument(
        "--no-points",
        action="store_true",
        help="Omit measurement points — geometry and per-vertex scalars only.",
    )
    args = parser.parse_args(argv)

    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import EPMapModel
    from pulse_ep.core.openep import write_userdata_payload
    from pulse_ep.core.openep_io import stored_userdata

    out = Path(args.output or f"map{args.map_id}.mat")
    with get_db_session() as session:
        model = session.get(EPMapModel, args.map_id)
        if model is None:
            print(f"no map with id {args.map_id}", file=sys.stderr)
            return 2
        try:
            userdata = stored_userdata(
                session,
                model,
                include_points=not args.no_points,
                include_signals=args.include_signals,
                ecg_channels=args.ecg_channels.split(",")
                if args.ecg_channels is not None
                else None,
                signal_scale_to_mv=args.signal_scale_to_mv,
                ablation_scope=args.ablation_scope,
                ablation_ids=[int(x) for x in args.ablation_ids.split(",")]
                if args.ablation_ids
                else None,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        notes = write_userdata_payload(userdata, out)
        map_name = model.map_name

    print(f"wrote {out} — map {map_name!r}")
    # Printed, not buried in the file: a reader who does not open MATLAB should
    # still learn what the structure could not carry.
    for note in notes[1:]:
        print(f"  note: {note}")
    if not notes[1:]:
        print("  every slot OpenEP has was filled")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
