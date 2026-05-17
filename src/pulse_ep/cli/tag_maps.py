"""
Auto-tag maps with attributes inferred from map name AND 3D coordinates.

Detection layers (in order of priority):
  1. Name-based  — atrium (LA/RA), region, map type
  2. Data-based  — pacemapping detection (ACT sign-flipped values in [0, 100])
  3. Coordinate-based — for Vera sub-regions: compute offset Δ from the study's
                        "Vera alles" centroid; thresholds derived from real data.

Usage
-----
  python tag_maps.py              # dry-run: print what would be set
  python tag_maps.py --apply      # write to database
  python tag_maps.py --study STR  # limit to studies containing STR
  python tag_maps.py --skip-existing --apply
"""

import argparse
import re

import numpy as np

from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import EPMapAttributes, EPMapModel, EPMapPoint

# ── CLI ────────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true", help="Write to DB (default: dry-run)")
ap.add_argument(
    "--skip-existing", action="store_true", help="Skip maps with attributes already set"
)
ap.add_argument("--study", default=None, help="Filter to study names containing this substring")
args = ap.parse_args()

SENTINEL = -9999.0


def _get_xyz_from_points(session, map_id) -> np.ndarray | None:
    """Build xyz array from EPMapPoint positions for a given map."""
    points = (
        session.query(EPMapPoint.position_x, EPMapPoint.position_y, EPMapPoint.position_z)
        .filter(EPMapPoint.map_id == map_id)
        .order_by(EPMapPoint.point_index)
        .all()
    )
    if not points:
        return None
    arr = np.array([[p[0] or np.nan, p[1] or np.nan, p[2] or np.nan] for p in points])
    if np.all(np.isnan(arr)):
        return None
    return arr


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 1 – Name-based detection
# ══════════════════════════════════════════════════════════════════════════════


def name_detect_atrium(name: str, study: str) -> str | None:
    t = (name + " " + study).upper()
    if re.search(r"\bVT\b", t):
        return "LV"
    if re.search(r"\bLA\b|LEFT[\s_-]*ATRI|RE[-]?LA\b", t):
        return "LA"
    if re.search(r"\bRA\b|RIGHT[\s_-]*ATRI|RE[-]?RA\b", t):
        return "RA"
    # "Vera" sub-regions are always the left atrium in AF ablation context
    if re.search(r"\bVERA\b", t):
        return "LA"
    return None


# ── Name corrections: RA has no "anterior wall" — it's always lateral ──
# Applied before pattern matching to fix known CARTO naming errors.
_NAME_FIXES = [
    # (atrium_pattern, wrong_part_pattern, corrected_label)
    (r"\bRA\b", r"ANT(?:ERIOR)?", "lateral wall"),
]

_PART_PATTERNS = [
    # Full map / no specific sub-region
    (r"\bALLES\b|\bALL\b|\bFULL\b", None),  # German "alles" = all
    # Sub-regions (checked before generic anterior/posterior)
    (r"POST(?:ERIOR)?[\s_-]*INF(?:ERIOR)?|POST[\s_-]*INF", "posterior inferior wall"),
    (r"POST(?:ERIOR)?[\s_-]*WALL|[\s_-]PW\b", "posterior wall"),
    (r"ANT(?:ERIOR)?[\s_-]*WALL|[\s_-]AW\b", "anterior wall"),
    (r"LAT(?:ERAL)?[\s_-]*WALL", "lateral wall"),
    (r"\bROOF\b|\bDACH\b", "roof"),  # German "Dach" = roof
    (r"\bFLOOR\b|\bBODEN\b", "floor"),
    (r"SEPT(?:AL)?[\s_-]*WALL?|[\s_-]SEP\b", "septal wall"),
    (r"INF(?:ERIOR)?[\s_-]*WALL", "inferior wall"),
    (r"\bISTHMUS\b", "isthmus"),
    # Short keywords without "wall" — only if standing alone to avoid false matches
    (r"[\s_-]POST\b|^POST\b|\bPOSTERIOR\b", "posterior wall"),
    (r"[\s_-]ANT\b|^ANT\b|\bANTERIOR\b", "anterior wall"),
    (r"[\s_-]LAT\b|^LAT\b|\bLATERAL\b", "lateral wall"),
    (r"[\s_-]SEP\b|^SEP\b|\bSEPTAL\b", "septal wall"),
    (r"\bINFERIOR\b", "inferior wall"),
]

_PART_SENTINEL = "__NONE__"  # marks "full map, no region"


def name_detect_part(name: str, atrium: str | None = None) -> str | None:
    """
    Return the detected region label, None if unclear, or _PART_SENTINEL if
    explicitly 'all / alles' (full map, no specific sub-region).

    If atrium is known, applies name corrections first (e.g. RA has no
    anterior wall → always lateral).
    """
    t = name.upper()

    # Check name corrections based on atrium
    if atrium:
        for atrium_pat, wrong_pat, corrected in _NAME_FIXES:
            if re.search(atrium_pat, atrium.upper()) and re.search(wrong_pat, t):
                return corrected

    for pattern, label in _PART_PATTERNS:
        if re.search(pattern, t):
            return label if label is not None else _PART_SENTINEL
    return None


_TYPE_PATTERNS = [
    # Must come before generic 'pace' to avoid partial matches
    (
        r"\bICPM\b|IC[\s_-]*PM\b|IC[\s_-]*PACE|IC[\s_-]*PATTERN|PATTERN[\s_-]*MATCH"
        r"|PACE[\s_-]*MAP\b|PACE[\s_-]*PATTERN\b|PACEMAP\b|PACEPM",
        "pacemapping",
    ),
    (r"\bAFIB\b|AF\b|ATRIAL\s+FIB", "AFIB"),
    (r"\bAFL\b|FLUTTER|ATRIAL\s+FLUTTER", "flutter"),
    (r"\bVT\b|VENTRICULAR\s+TACH", "VT"),
    (r"\bBIPOLAR\b", "voltage"),
    (r"\bSR\b|\bSINUS\b", "activation-SR"),
    (r"\bRPV\b|\bLPV\b|\bPVI\b|PULMONARY\s+VEIN", "PV-isolation"),
    (r"RE[\s_-]?(LA|RA|IC|PV)\b|REANNOTATION", "reannotation"),
]


def name_detect_type(name: str) -> str | None:
    t = name.upper()
    for pattern, label in _TYPE_PATTERNS:
        if re.search(pattern, t):
            return label
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 2 – ACT data-based pacemapping detection
# ══════════════════════════════════════════════════════════════════════════════


def data_is_pacemapping(act_bip_raw) -> tuple[bool | None, str]:
    """
    Returns (result, reason).  result = True/False/None (None = no data).
    Applies the same sign-flip as extract_mesh_data: negate if max < 0.
    """
    if act_bip_raw is None:
        return None, "no act_bip data"
    arr = np.array(act_bip_raw, dtype=float)
    act = arr[:, 0] if arr.ndim == 2 else arr
    valid = act[(act > SENTINEL) & ~np.isnan(act)]
    if not len(valid):
        return None, "no valid ACT values"

    if np.nanmax(valid) < 0:
        valid = -valid  # same sign flip as extract_mesh_data

    mn, mx = float(valid.min()), float(valid.max())

    # ACT values contain sentinel 10000 → not a real map
    if mn > 9000:
        return False, f"sentinel values only (ACT={mn:.0f})"

    is_pm = mn >= 0 and mx <= 100
    reason = f"ACT [{mn:.1f}–{mx:.1f}]  {'✓ in [0,100]' if is_pm else '✗ outside [0,100]'}"
    return is_pm, reason


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 3 – Coordinate-based region detection for Vera sub-regions
# ══════════════════════════════════════════════════════════════════════════════


def _centroid(raw, ncols=3) -> np.ndarray | None:
    if raw is None:
        return None
    arr = np.array(raw, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, ncols)
    v = arr[~np.any(np.isnan(arr), axis=1)]
    return np.mean(v, axis=0) if len(v) else None


# Thresholds derived from 9 patients (see coordinate offset analysis)
_LAT_X_THRESH = +15.0  # ΔX > +15 → lateral
_SEP_X_THRESH = -10.0  # ΔX < -10 → septal or Dach
_ANT_Y_THRESH = +5.0  # ΔY > +5 with small ΔX → anterior or Dach
_POST_Y_THRESH = -5.0  # ΔY < -5 with small ΔX → posterior inferior
_POST_Z_THRESH = -8.0  # ΔZ < -8 → inferior (distinguishes post-inf from septal)
_ANT_Z_THRESH = +5.0  # ΔZ > +5 → superior (characteristic of anterior)


def coord_detect_part(map_xyz, reference_centroid) -> str | None:
    """
    Classify a Vera sub-region map based on its offset from the 'Vera alles'
    centroid.  Returns a region label or None if classification is uncertain.

    Δ = centroid(map_xyz) - reference_centroid
    Patterns validated across 9 patients:
      lateral:          ΔX > +15
      Dach (roof):      ΔX < -10  AND  ΔY > +5
      septal:           ΔX < -10  AND  ΔY < 0
      anterior:         ΔX small  AND  ΔY > +5  AND  ΔZ > +5
      post. inferior:   ΔX small  AND  ΔY < -5  AND  ΔZ < -8
    """
    c = _centroid(map_xyz)
    if c is None or reference_centroid is None:
        return None

    d = c - reference_centroid
    dx, dy, dz = d[0], d[1], d[2]

    if dx > _LAT_X_THRESH:
        return "lateral wall"
    if dx < _SEP_X_THRESH:
        if dy > _ANT_Y_THRESH:
            return "roof"
        if dy < 0:
            return "septal wall"
    # Small ΔX
    if dy > _ANT_Y_THRESH and dz > _ANT_Z_THRESH:
        return "anterior wall"
    if dy < _POST_Y_THRESH and dz < _POST_Z_THRESH:
        return "posterior inferior wall"
    return None  # uncertain


# ══════════════════════════════════════════════════════════════════════════════
#  Combine all layers → final attribute dict for a map
# ══════════════════════════════════════════════════════════════════════════════


def build_attributes(m, vera_alles_centroid, xyz=None) -> dict:
    """Return the dict of attributes we want to set for this map."""

    # ── Layer 1: name
    atrium = name_detect_atrium(m.map_name, m.study_name)
    part_name = name_detect_part(m.map_name, atrium=atrium)
    type_name = name_detect_type(m.map_name)

    # ── Layer 2: ACT data
    data_pm, data_reason = data_is_pacemapping(m.act_bip)

    # Determine final type and pacemap flag
    # If name says pacemapping → trust name; data is used to confirm.
    # If name says activation/AFIB/SR/voltage → NOT pacemapping (override data).
    # These types always override the data-based PM detection.
    # 'reannotation' and 'PV-isolation' are NOT listed — a re-isolation map
    # can still be a pacemapping map if the ACT data confirms it.
    non_pm_types = {"AFIB", "flutter", "VT", "voltage", "activation-SR"}
    is_vera = bool(re.search(r"\bVERA\b", m.map_name.upper()))

    if type_name == "pacemapping":
        final_type = "pacemapping"
        final_pacemap = True
    elif type_name in non_pm_types:
        final_type = type_name
        final_pacemap = False
    elif data_pm is True and not is_vera:
        # Data says PM and no strong contradicting name keyword
        final_type = "pacemapping"
        final_pacemap = True
    else:
        final_type = type_name  # could be None
        final_pacemap = None  # unknown

    # ── Layer 3: coordinate-based region for Vera sub-regions
    # "alles" maps ARE the spatial reference — never classify them via coordinates.
    is_alles = part_name == _PART_SENTINEL
    coord_part = None
    if is_vera and not is_alles and vera_alles_centroid is not None:
        coord_part = coord_detect_part(xyz, vera_alles_centroid)

    # Decide final part
    if is_alles:
        final_part = "full"  # "alles" = whole chamber mapped
    elif part_name is not None:
        final_part = part_name
    elif coord_part is not None:
        final_part = coord_part  # fallback to coordinates
    else:
        final_part = None

    # Build attribute dict (only include keys with values)
    attrs = {}
    if atrium:
        attrs["atrium"] = atrium
    if final_part:
        attrs["part"] = final_part
    if final_type:
        attrs["type"] = final_type
    if final_pacemap is True:
        attrs["pacemap"] = True
    if final_pacemap is False:
        attrs["pacemap"] = False

    return attrs, data_reason, coord_part


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════


def main():
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'=' * 70}")
    print(f"  tag_maps.py  [{mode}]")
    print(f"{'=' * 70}\n")

    with get_db_session() as session:
        maps = session.query(EPMapModel).order_by(EPMapModel.study_name, EPMapModel.map_name).all()

        if args.study:
            maps = [m for m in maps if args.study.lower() in m.study_name.lower()]
        print(f"Processing {len(maps)} maps\n")

        # Pre-compute per-study "Vera alles" reference centroids
        vera_refs: dict[str, np.ndarray | None] = {}
        for m in maps:
            if re.search(r"\bVERA\b.*\bALLES\b|\bVERA\s+ALLES\b", m.map_name.upper()):
                xyz = _get_xyz_from_points(session, m.id)
                c = _centroid(xyz)
                if c is not None:
                    vera_refs[m.study_name] = c

        changed = 0
        for m in maps:
            attr_entry = session.query(EPMapAttributes).filter_by(map_id=m.id).first()
            existing = attr_entry.attributes if attr_entry else {}

            if args.skip_existing and existing:
                continue

            vera_ref = vera_refs.get(m.study_name)
            # Only load xyz from points if coordinate detection is needed
            is_vera = bool(re.search(r"\bVERA\b", m.map_name.upper()))
            xyz = _get_xyz_from_points(session, m.id) if is_vera and vera_ref is not None else None
            new_attrs, data_reason, coord_part = build_attributes(m, vera_ref, xyz=xyz)

            # Print summary
            print(f"[{m.id:>4}] {m.map_name}")
            print(f"       study  : {m.study_name}")
            print(f"       ACT    : {data_reason}")
            if coord_part:
                print(f"       coord  : {coord_part}")
            if existing:
                print(f"       existed: {existing}")
            if new_attrs:
                print(f"       → set  [{m.map_name}]: {new_attrs}")
            else:
                print(f"       → nothing detected [{m.map_name}]")
            print()

            if args.apply and new_attrs:
                if attr_entry is None:
                    attr_entry = EPMapAttributes(map_id=m.id, attributes={})
                    session.add(attr_entry)
                attr_entry.set_attributes(new_attrs)
                changed += 1

        if args.apply:
            session.commit()
            print(f"Committed attributes for {changed} maps.")
        else:
            print("Dry-run complete — re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
