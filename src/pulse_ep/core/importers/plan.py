"""The vendor-neutral import plan.

``prepare(source) -> ImportPlan`` proposes what would be imported with
sensible defaults and detected issues (no DB writes); a human reviews /
adjusts it; ``commit(plan, source)`` executes it. This is the single place
"pre-fill as much as sensibly possible" lives, and it works the same for
CARTO and EnSiteX.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MapPlan:
    """One proposed EP map (a bi/uni group is one map)."""

    map_name: str
    files: list[str]
    part: str | None = None  # endo / epi
    scalar_fields: dict[str, str] = field(default_factory=dict)  # field name -> kind
    n_vertices: int | None = None
    include: bool = True  # default selection
    issues: list[str] = field(default_factory=list)


@dataclass
class WaveformPlan:
    """Optional signal data — opt-in, default OFF (can dwarf the export)."""

    files: list[str] = field(default_factory=list)
    estimated_bytes: int = 0
    include: bool = False
    format: str = "parquet"
    #: "reference" = keep source export + extract on demand; "cache" = write Parquet copy.
    storage: str = "reference"


@dataclass
class StudyPlan:
    study_name: str
    vendor: str
    provenance: dict = field(default_factory=dict)
    maps: list[MapPlan] = field(default_factory=list)
    waveforms: WaveformPlan = field(default_factory=WaveformPlan)


@dataclass
class ImportPlan:
    studies: list[StudyPlan] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
