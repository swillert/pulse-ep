"""Exports that are not a full study: waveforms only, no geometry.

A real EnSite X export turned up carrying nothing but DxL point tables and
waveform CSVs — no DIF model at all. It imported as an empty study and
reported success, and its waveforms were reported as "0 files" because they
use a naming scheme the globs did not cover.
"""

from __future__ import annotations

import io
from pathlib import Path

from pulse_ep.core.importers.ensite import EnsiteImporter

# The preamble a DxL export carries; the parser locates the data by
# "Data starts in row", so the exact leading lines matter less than the count.
_WAVE_CSV = """Export File Version: 11
Export Data Element: DxL
Exported from Software Version: 6.0.0.683129
Export from Study: synthetic
Data starts in row,7

Map name:,synthetic map
Wave name:,rov
"""


class _MemorySource:
    """The smallest ImportSource that the planner needs: names and bytes."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def list(self, pattern: str | None = None) -> list[str]:
        from fnmatch import fnmatch

        names = sorted(self._files)
        return [n for n in names if pattern is None or fnmatch(n, pattern)]

    def open(self, name: str):
        return io.BytesIO(self._files[name])

    def size(self, name: str) -> int:
        return len(self._files[name])

    def materialize(self, members=None) -> Path:  # pragma: no cover - unused here
        raise NotImplementedError


def _waveform_only_source() -> _MemorySource:
    body = _WAVE_CSV.encode()
    return _MemorySource(
        {
            # This export's naming: Wave_<channel>.csv, not *_Waveforms_*.csv
            "study/Contact_Mapping/Wave_rov.csv": body,
            "study/Contact_Mapping/Wave_refs.csv": body,
            "study/Contact_Mapping/Wave_uni_distal.csv": body,
            "study/Contact_Mapping/Map_Score_bi.csv": body,
        }
    )


def test_wave_named_files_count_as_waveforms():
    """Both naming schemes are waveforms; matching only one reported zero."""
    plan = EnsiteImporter().prepare(_waveform_only_source())
    (study,) = plan.studies
    assert len(study.waveforms.files) == 3
    assert study.waveforms.estimated_bytes > 0
    assert study.waveforms.include is False  # still opt-in


def test_underscore_waveforms_naming_still_matches():
    source = _MemorySource(
        {
            "study/ECG_Waveforms_Raw.csv": _WAVE_CSV.encode(),
            "study/EP_Catheter_Bipolar_Waveforms_Filtered.csv": _WAVE_CSV.encode(),
        }
    )
    (study,) = EnsiteImporter().prepare(source).studies
    assert len(study.waveforms.files) == 2


def test_export_without_geometry_says_so():
    """No mesh, no anatomy: the plan must state that nothing can be imported."""
    plan = EnsiteImporter().prepare(_waveform_only_source())
    (study,) = plan.studies
    assert study.maps == []
    assert plan.issues, "an export with no geometry must carry an issue"
    text = " ".join(plan.issues).lower()
    assert "no geometry" in text
    assert "waveform" in text  # says what it *did* find


def test_a_normal_export_carries_no_such_issue():
    """The warning must not fire for an export that has a model."""
    source = _MemorySource(
        {
            "study/Model_Groups.xml": b"<DIF></DIF>",
            "study/ECG_Waveforms_Raw.csv": _WAVE_CSV.encode(),
        }
    )
    plan = EnsiteImporter().prepare(source)
    assert not [i for i in plan.issues if "no geometry" in i.lower()]
