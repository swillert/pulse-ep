"""The vendor-neutral import plan.

``prepare(source) -> ImportPlan`` proposes what would be imported with
sensible defaults and detected issues (no DB writes); a human reviews /
adjusts it; ``commit(plan, source)`` executes it. This is the single place
"pre-fill as much as sensibly possible" lives, and it works the same for
CARTO and EnSite X.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass
class MapPlan:
    """One proposed EP map (a bi/uni group is one map)."""

    map_name: str
    files: list[str]
    part: str | None = None  # endo / epi
    scalar_fields: dict[str, str] = field(default_factory=dict)  # field name -> kind
    n_vertices: int | None = None
    points_files: list[str] = field(default_factory=list)  # Map_PP_*.csv for this map
    include: bool = True  # default selection
    include_points: bool = True  # per-point measurements (default on)
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
    placed_point_files: list[str] = field(default_factory=list)  # AutoMark/Lesions/Labels
    include_placed_points: bool = True
    anatomy_files: list[str] = field(default_factory=list)  # Model_Groups.xml
    #: Names of the volumes inside those files. One EnSite X anatomy file holds
    #: nine — endocardium, six wall-thickness shells, channels, fat — and a
    #: reviewer shown only a file count cannot tell that from a single chamber.
    anatomy_volumes: list[str] = field(default_factory=list)
    include_anatomy: bool = True


@dataclass
class ImportPlan:
    studies: list[StudyPlan] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def plan_to_dict(plan: ImportPlan) -> dict:
    """JSON-serialisable form of a plan (for storing on an import job)."""
    return dataclasses.asdict(plan)


def plan_from_dict(d: dict) -> ImportPlan:
    """Rebuild an :class:`ImportPlan` from :func:`plan_to_dict` output.

    Reconstructs the reviewer's edited selections (include flags, etc.).
    """
    studies = []
    for s in d.get("studies", []):
        studies.append(
            StudyPlan(
                study_name=s["study_name"],
                vendor=s["vendor"],
                provenance=s.get("provenance") or {},
                maps=[MapPlan(**m) for m in s.get("maps", [])],
                waveforms=WaveformPlan(**(s.get("waveforms") or {})),
                placed_point_files=s.get("placed_point_files", []),
                include_placed_points=s.get("include_placed_points", True),
                anatomy_files=s.get("anatomy_files", []),
                anatomy_volumes=s.get("anatomy_volumes", []),
                include_anatomy=s.get("include_anatomy", True),
            )
        )
    return ImportPlan(studies=studies, issues=d.get("issues", []))
