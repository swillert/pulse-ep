"""Abbott EnSiteX (St. Jude) DIF decode.

Parses the ``SJM_DIF_5.0`` XML meshes (``Contact_Mapping_Model*.xml``,
``Model_Groups.xml``) into vendor-neutral geometry + scalar fields.

Verified DIF quirks handled here (see the project notes):
- ``<Polygons>`` indices are **1-based** — converted to 0-based.
- ``<AP_MapViewMatrix>`` is a *display* transform and is NOT applied to the
  stored coordinates; ``<Rotation>/<Scaling>/<Translation>`` are kept as
  registration metadata (identity in the samples seen).
- ``<Map_data>`` is one scalar per vertex (voltage, mV); ``<Map_status>``
  codes ``0`` = valid, ``2`` = interpolated → per-scalar validity mask.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from lxml import etree

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR, VOLTAGE_UNIPOLAR


@dataclass
class DifVolume:
    """One ``<Volume>`` decoded from a DIF file."""

    name: str
    vertices: np.ndarray  # (N, 3)
    triangles: np.ndarray  # (M, 3), 0-based
    normals: np.ndarray | None = None
    map_data: np.ndarray | None = None  # (N,) per-vertex scalar
    status_mask: np.ndarray | None = None  # (N,) bool, True = valid (not interpolated)
    color_high_low: tuple[float, float] | None = None
    rotation: np.ndarray | None = None
    scaling: np.ndarray | None = None
    translation: np.ndarray | None = None
    labels: list[str] = field(default_factory=list)


def _floats(elem) -> np.ndarray | None:
    if elem is None or elem.text is None:
        return None
    return np.fromstring(elem.text, sep=" ")


def parse_dif(xml: bytes | str) -> list[DifVolume]:
    """Parse DIF XML bytes into one :class:`DifVolume` per ``<Volume>``."""
    data = xml.encode() if isinstance(xml, str) else xml
    root = etree.fromstring(data)

    volumes: list[DifVolume] = []
    for vol in root.findall(".//Volume"):
        verts = _floats(vol.find("Vertices"))
        polys = _floats(vol.find("Polygons"))
        if verts is None or polys is None:
            continue
        verts = verts.reshape(-1, 3)
        triangles = polys.astype(np.int64).reshape(-1, 3) - 1  # 1-based → 0-based

        normals = _floats(vol.find("Normals"))
        if normals is not None:
            normals = normals.reshape(-1, 3)

        map_data = _floats(vol.find("Map_data"))
        status = _floats(vol.find("Map_status"))
        status_mask = None if status is None else (status == 0.0)

        chl = _floats(vol.find("Color_high_low"))
        color_high_low = (float(chl[0]), float(chl[1])) if chl is not None and chl.size >= 2 else None

        labels = [le.text.strip() for le in vol.findall(".//Label") if le.text]

        volumes.append(
            DifVolume(
                name=vol.get("name") or "",
                vertices=verts,
                triangles=triangles,
                normals=normals,
                map_data=map_data,
                status_mask=status_mask,
                color_high_low=color_high_low,
                rotation=_floats(vol.find("Rotation")),
                scaling=_floats(vol.find("Scaling")),
                translation=_floats(vol.find("Translation")),
                labels=labels,
            )
        )
    return volumes


# --- filename descriptor ---------------------------------------------------

_TYPE_TOKENS = (
    "voltage", "remap", "premap", "vt", "stim", "lvstim", "rvstim", "deep", "pre",
)


def parse_map_descriptor(filename: str) -> dict:
    """Decode an EnSite map filename into part / polarity / type tokens.

    Tolerant and token-based — EnSite naming is inconsistent across sites
    (``Endo_Voltage_Pre-bi`` vs ``PreMap-unipolar``) — never hard-fails; the
    raw stem is always kept.
    """
    stem = Path(filename).stem
    body = re.sub(r"^Contact_Mapping_Model_?", "", stem, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"[_\-\s]+", body) if t]
    low = [t.lower() for t in tokens]

    desc: dict = {"raw_name": stem}
    if "endo" in low:
        desc["part"] = "endo"
    elif "epi" in low:
        desc["part"] = "epi"

    polarity = None
    for t in low:
        if t.startswith("uni"):
            polarity = "unipolar"
        elif t.startswith("bi"):
            polarity = "bipolar"
    desc["polarity"] = polarity

    types = [t for t in low if any(t == tok or tok in t for tok in _TYPE_TOKENS)]
    if types:
        desc["type_tokens"] = types
    return desc


def scalar_kind_for(descriptor: dict) -> tuple[str, str]:
    """Return ``(field_name, kind)`` for a DIF map's ``Map_data``.

    DIF contact-mapping models carry voltage (mV); polarity comes from the
    descriptor (defaulting to bipolar). Activation/other map types would need
    value-range detection — a later refinement, not assumed here.
    """
    if descriptor.get("polarity") == "unipolar":
        return "voltage_unipolar", VOLTAGE_UNIPOLAR
    return "voltage_bipolar", VOLTAGE_BIPOLAR


def dif_to_epmap(volume: DifVolume, descriptor: dict, study_name: str, source: str) -> EPMap:
    """Build a vendor-neutral :class:`EPMap` from one DIF volume."""
    epmap = EPMap(
        map_name=descriptor["raw_name"],
        study_name=study_name,
        vertices=volume.vertices,
        triangles=volume.triangles,
        normals=volume.normals,
    )
    if volume.map_data is not None:
        name, kind = scalar_kind_for(descriptor)
        epmap.register_scalar(
            name, volume.map_data, kind=kind, status_mask=volume.status_mask, source=source
        )
    return epmap
