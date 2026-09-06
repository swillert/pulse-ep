"""The shipped synthetic exports must survive the whole decode path.

These fixtures are the only vendor exports in the repository: the real ones
are patient data and stay out. Their *structure* is taken from real CARTO 3 and
EnSiteX exports (see ``tools/make_synthetic_fixtures.py``), their content is
generated — so they pin the reader's handling of the file layout, not the
clinical meaning of any field. ``tests/fixtures/synthetic/README.md`` says
exactly what that does and does not establish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pulse_ep.core.importers  # noqa: F401  — registers the vendor importers
from pulse_ep.core.importers.base import commit_plan, detect_vendor, prepare_plan
from pulse_ep.core.importers.source import source_for

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"

# What each export is known to contain. The counts come from the generator,
# so a reader that starts dropping rows — the off-by-one that a hand-written
# colours section originally caused — fails here instead of on real data.
EXPECTED = {
    "ensite": {
        "vendor": "ensite",
        "map_name": "Contact_Mapping_Model",
        "vertices": 962,
        "triangles": 1920,
        "fields": {"voltage_bipolar"},
        "points": 64,
        "measurements": {"voltage_bipolar"},
    },
    "carto": {
        "vendor": "carto",
        "map_name": "1-1-1-Synthetic Left Atrium",
        "vertices": 962,
        "triangles": 1920,
        "fields": {"activation_time", "voltage_bipolar"},
        "points": 64,
        "measurements": {"activation_time", "voltage_bipolar", "voltage_unipolar"},
    },
}


@pytest.fixture(scope="module", params=sorted(EXPECTED))
def decoded(request):
    """(expectation, the single map decoded from that vendor's fixture)."""
    want = EXPECTED[request.param]
    export = FIXTURES / request.param / "synthetic_study"
    if not export.is_dir():
        pytest.skip(f"fixture not generated: {export}")

    source = source_for(export)
    importer = detect_vendor(source)
    assert importer is not None, f"no importer recognised {export}"
    assert importer.name == want["vendor"]

    studies = commit_plan(importer, prepare_plan(importer, source), source)
    maps = [m for s in studies for m in s.epmaps]
    assert len(maps) == 1, f"expected one map, got {[m.map_name for m in maps]}"
    return want, maps[0]


def test_mesh_is_read_completely(decoded):
    want, epmap = decoded
    assert epmap.map_name == want["map_name"]
    assert len(epmap.vertices) == want["vertices"]
    assert len(epmap.triangles) == want["triangles"]


def test_scalar_fields_are_named_by_quantity(decoded):
    want, epmap = decoded
    assert set(epmap.scalar_fields) == want["fields"]
    for name, field in epmap.scalar_fields.items():
        assert len(field.values) == want["vertices"], f"{name} has the wrong length"


def test_measurement_points_carry_positions_and_values(decoded):
    """Every point needs a position: a point without one is silently dropped.

    That is not hypothetical — the core import path lost *all* CARTO points
    this way, because coordinates live in the study catalogue rather than in
    the per-point export, and only the CLI backfilled them.
    """
    want, epmap = decoded
    points = epmap.measurement_points
    assert len(points) == want["points"]
    for p in points:
        assert p.position is not None and len(p.position) == 3
    assert want["measurements"] <= set(points[0].measurements)


def test_areas_are_computable(decoded):
    """The decode has to reach the analysis layer, not just fill arrays."""
    _want, epmap = decoded
    epmap.generate_anatomical_pv_mesh(simplify=False)
    epmap.precompute_areas()
    assert epmap.area_of_surface() > 0


def test_both_vendors_describe_the_same_surface():
    """Same geometry, two vendor formats, one answer.

    The generator writes one synthetic mesh into both export formats, so a
    difference in the computed area beyond the formats' own precision is a
    difference in how the two readers decode coordinates or triangles — the
    one comparison these fixtures can make that a single-vendor test cannot.

    The tolerance is not arbitrary: a CARTO ``.mesh`` stores coordinates with
    three decimals (``47.460``), the DIF export with more, so the same surface
    cannot round-trip to the same number. The observed gap is ~3e-6 relative;
    anything at 1e-4 is a decode difference, not rounding.
    """
    areas = {}
    for vendor in EXPECTED:
        export = FIXTURES / vendor / "synthetic_study"
        if not export.is_dir():
            pytest.skip(f"fixture not generated: {export}")
        source = source_for(export)
        importer = detect_vendor(source)
        (epmap,) = [
            m
            for s in commit_plan(importer, prepare_plan(importer, source), source)
            for m in s.epmaps
        ]
        epmap.generate_anatomical_pv_mesh(simplify=False)
        epmap.precompute_areas()
        areas[vendor] = epmap.area_of_surface()

    carto, ensite = areas["carto"], areas["ensite"]
    assert carto == pytest.approx(ensite, rel=1e-4), (
        f"{areas} — readers disagree on the same surface"
    )
