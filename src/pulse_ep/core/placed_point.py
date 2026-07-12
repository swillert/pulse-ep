"""Placed points — operator/system markers set on a study (vendor-neutral).

Distinct from :class:`MeasurementPoint` (an acquisition sample): a placed
point is an *intentional* marker — an ablation site, an anatomical landmark,
a tag — carrying a ``type`` from a controlled vocabulary plus an OPEN
``attributes`` map for type-specific data. Study-level (a physical location
in the shared study frame), not tied to one map's mesh.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# controlled vocabulary of placed-point types
ABLATION = "ablation"  # RF / PFA / cryo therapy site
LANDMARK = "landmark"  # anatomical landmark
REFERENCE = "reference"  # reference / pacing site
MARKER = "marker"  # generic placed marker (e.g. 3DE)
TAG = "tag"  # free annotation
SHADOW = "shadow"  # frozen catheter shadow
TAPE_MEASURE = "tape_measure"


@dataclass
class PlacedPoint:
    """An operator/system-placed marker in the study coordinate frame."""

    type: str
    position: np.ndarray  # (3,)
    label: str | None = None
    attributes: dict = field(default_factory=dict)  # open, type-specific
    source_id: str | None = None
