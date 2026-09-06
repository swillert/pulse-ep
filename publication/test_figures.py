"""The publication figures must stay reproducible from a clean checkout.

Every figure is generated from the two synthetic exports in
``tests/fixtures/synthetic/``. If this test fails, a figure in the paper can
no longer be produced by the code that is being published alongside it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = HERE / "make_figures.py"

# Every figure the paper refers to, by the name the script gives it.
FIGURES = (
    "map_carto.png",
    "map_ensite.png",
    "area_per_interval.png",
    "cross_vendor_delta.png",
    "scalar_histograms.png",
)


def _no_offscreen_gl(stderr: str) -> bool:
    """True if the failure is a missing software GL stack, not a code fault."""
    markers = ("OSMesa", "libOSMesa", "Failed to load EGL", "bad X server connection")
    return any(m in stderr for m in markers)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run the real script into a temporary directory, exactly as documented."""
    pytest.importorskip("pyvista")
    if not (REPO / "tests" / "fixtures" / "synthetic" / "carto").is_dir():
        pytest.skip("synthetic fixtures not present")

    out = tmp_path_factory.mktemp("figures")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if proc.returncode != 0 and _no_offscreen_gl(proc.stderr):
        # VTK dies with a signal rather than an error when there is no GL
        # stack at all. That is the machine's, not the script's, so say so
        # plainly instead of reporting a broken figure pipeline.
        pytest.skip(f"no off-screen GL on this machine (rc={proc.returncode})")
    assert proc.returncode == 0, proc.stderr[-4000:]
    return out, proc.stdout


@pytest.mark.parametrize("name", FIGURES)
def test_figure_is_produced(generated, name):
    out, _stdout = generated
    path = out / name
    assert path.is_file(), f"{name} was not written"
    # A PyVista render that fails silently still writes a file, so check the
    # PNG is a plausible image rather than an empty or truncated one.
    assert path.stat().st_size > 10_000, f"{name} is suspiciously small"
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG"


def test_the_two_vendors_still_agree(generated):
    """The residual the cross-vendor figure shows must stay at rounding level.

    The script prints it; a regression in either reader would move it by
    orders of magnitude, and the figure's caption would become wrong.
    """
    _out, stdout = generated
    line = next(ln for ln in stdout.splitlines() if "cross-vendor residual" in ln)
    residual = float(line.split("=")[1].strip().split()[0])
    assert residual < 1e-3, f"readers disagree beyond format precision: {line}"
