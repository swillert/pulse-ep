#!/usr/bin/env bash
# Check a pulse-ep installation against the two shipped synthetic exports.
#
# Reads one CARTO 3 and one EnSiteX export from tests/fixtures/synthetic/,
# decodes each one, and prints what came out. No database, no server and no
# patient data are involved — see tests/fixtures/synthetic/README.md for what
# a green run does and does not establish.
#
# Usage:  examples/verify.sh            (uses the python on PATH)
#         PYTHON=.venv/bin/python examples/verify.sh
set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$ROOT/tests/fixtures/synthetic"

if [ ! -d "$FIXTURES" ]; then
    echo "Fixtures missing: $FIXTURES" >&2
    exit 1
fi

"$PYTHON" - "$FIXTURES" <<'PY'
import sys
from pathlib import Path

import pulse_ep.core.importers  # noqa: F401  — registers the vendor importers
from pulse_ep.core.importers.base import commit_plan, detect_vendor, prepare_plan
from pulse_ep.core.importers.source import source_for

fixtures = Path(sys.argv[1])
failures = []

for vendor in ("carto", "ensite"):
    export = fixtures / vendor / "synthetic_study"
    print(f"\n=== {vendor} — {export.relative_to(fixtures.parent.parent.parent)} ===")
    try:
        source = source_for(export)
        importer = detect_vendor(source)
        if importer is None:
            raise RuntimeError("no importer recognised this export")
        print(f"  vendor erkannt: {importer.name}")

        for study in commit_plan(importer, prepare_plan(importer, source), source):
            for epmap in study.epmaps:
                epmap.generate_anatomical_pv_mesh(simplify=False)
                epmap.precompute_areas()
                print(
                    f"  map {epmap.map_name}: "
                    f"{len(epmap.vertices)} Vertices, {len(epmap.triangles)} Dreiecke, "
                    f"{len(epmap.measurement_points)} Messpunkte"
                )
                print(f"    Felder: {', '.join(sorted(epmap.scalar_fields)) or '—'}")
                print(f"    Fläche: {epmap.area_of_surface():.3f} cm²")
    except Exception as exc:
        failures.append(f"{vendor}: {exc}")
        print(f"  FEHLER: {exc}")

print()
if failures:
    print("FEHLGESCHLAGEN:")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("Beide Exporte wurden vollständig gelesen.")
PY
