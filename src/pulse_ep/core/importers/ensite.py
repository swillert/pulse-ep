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

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.importers.base import register_importer
from pulse_ep.core.importers.plan import ImportPlan, MapPlan, StudyPlan, WaveformPlan
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.scalar_field import VOLTAGE_BIPOLAR, VOLTAGE_UNIPOLAR
from pulse_ep.core.study import Study
from pulse_ep.core.waveform import Waveform


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


# --- bipolar / unipolar grouping -------------------------------------------

_POLARITY_SUFFIX = re.compile(r"[-_ ]?(bipolar|unipolar|bipol|unipol|bi|uni)$", re.IGNORECASE)


class GeometryMismatch(Exception):
    """Raised when maps grouped as one map do not share vertex geometry."""


def group_key(filename: str) -> str:
    """Descriptor minus polarity — the identity a bi/uni pair shares."""
    return _POLARITY_SUFFIX.sub("", Path(filename).stem)


def group_dif_files(names: list[str]) -> dict[str, list[str]]:
    """Group DIF filenames by :func:`group_key` (bi+uni of one map together)."""
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(group_key(name), []).append(name)
    return {k: sorted(v) for k, v in groups.items()}


def merge_dif_group(
    items: list[tuple[str, DifVolume]], study_name: str, source: str
) -> EPMap:
    """Merge one group's DIF volumes into a single multi-scalar :class:`EPMap`.

    bi and uni of the same map are separate files sharing identical geometry;
    they become one map carrying ``voltage_bipolar`` and ``voltage_unipolar``.

    :raises GeometryMismatch: if the grouped volumes' vertices differ — the
        caller should then keep them as separate maps rather than merge blindly.
    """
    base_name, base = items[0]
    epmap = EPMap(
        map_name=group_key(base_name),
        study_name=study_name,
        vertices=base.vertices,
        triangles=base.triangles,
        normals=base.normals,
    )
    for name, vol in items:
        if vol.vertices.shape != base.vertices.shape or not np.array_equal(
            vol.vertices, base.vertices
        ):
            raise GeometryMismatch(f"{name} geometry differs from {base_name}")
        if vol.map_data is None:
            continue
        field_name, kind = scalar_kind_for(parse_map_descriptor(name))
        epmap.register_scalar(
            field_name, vol.map_data, kind=kind, status_mask=vol.status_mask, source=source
        )
    return epmap


# --- waveforms -------------------------------------------------------------

_TIME_COLS = {"t_dws", "t_secs", "t_usecs", "t_ref"}


def _signal_type(name: str) -> str:
    n = name.lower()
    if "unipolar" in n:
        return "egm_unipolar"
    if "bipolar" in n:
        return "egm_bipolar"
    if "ecg" in n:
        return "ecg"
    return ""


def parse_ensite_waveforms(data: bytes | str, name: str = "") -> Waveform:
    """Parse an EnSite ``EP_Catheter_*_Waveforms`` / ``ECG_*`` CSV.

    The file has a preamble (filters, segment, study) then a header row
    starting ``t_dws,...`` and a sample matrix. Each channel is a triplet
    ``X`` / ``X_ds`` / ``X_ps``; only the base ``X`` column is the signal.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()

    meta: dict = {}
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("t_dws,"):
            header_idx = i
            break
        s = line.strip()
        if s and ":" in s and not s.startswith(("Catheter[", "Electrode[")):
            key, val = s.split(":", 1)
            meta[key.strip()] = val.strip()
    if header_idx is None:
        raise ValueError("no waveform data header (t_dws,...) found")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]

    signal_cols = [
        c for c in df.columns if c not in _TIME_COLS and not str(c).endswith(("_ds", "_ps"))
    ]
    # drop trailing partial rows that carry a timestamp but no signal samples
    df = df[~df[signal_cols].isna().all(axis=1)]
    signal = df[signal_cols].to_numpy(dtype=float)

    time = df["t_ref"].to_numpy(dtype=float) if "t_ref" in df.columns else None
    sample_rate = None
    if time is not None and time.size > 1:
        steps = np.diff(time)
        steps = steps[steps > 0]
        if steps.size:
            sample_rate = float(round(1.0 / float(np.median(steps))))

    filters = {k: meta[k] for k in ("Highpass", "Lowpass", "Notch") if k in meta}
    return Waveform(
        data=signal,
        channels=[str(c) for c in signal_cols],
        sample_rate=sample_rate,
        signal_type=_signal_type(name or meta.get("Export Data Element", "")),
        time=time,
        meta={
            "segment": meta.get("Export from Segment"),
            "study_guid": meta.get("Export from Study"),
            "software_version": meta.get("Exported from Software Version"),
            "filters": filters,
        },
    )


# --- vendor importer (prepare / commit over an ImportSource) ---------------

_MAP_GLOB = "*Contact_Mapping_Model*.xml"
_WAVEFORM_GLOBS = ("*Waveforms*.csv", "*ECG*.csv")
_VERT_RE = re.compile(rb'<Vertices number="(\d+)"')


def _vertex_count(source: ImportSource, name: str) -> int | None:
    """Cheap header scan for the vertex count (no full parse)."""
    with source.open(name) as fh:
        head = fh.read(16384)
    m = _VERT_RE.search(head)
    return int(m.group(1)) if m else None


def _read_provenance(source: ImportSource) -> dict:
    """Study GUID + software version from any CSV export preamble."""
    prov: dict = {}
    csvs = source.list("*.csv")
    if not csvs:
        return prov
    with source.open(csvs[0]) as fh:
        head = fh.read(2048).decode("utf-8", "ignore")
    for line in head.splitlines():
        if line.startswith("Exported from Software Version:"):
            prov["software_version"] = line.split(":", 1)[1].strip()
        elif line.startswith("Export from Study:"):
            prov["study_guid"] = line.split(":", 1)[1].strip()
    return prov


class EnsiteImporter:
    """Vendor importer for Abbott EnSiteX (St. Jude) DIF exports."""

    name = "ensite"

    def sniff(self, source: ImportSource) -> bool:
        difs = source.list(_MAP_GLOB) or source.list("*Model_Groups*.xml")
        if not difs:
            return False
        try:
            with source.open(difs[0]) as fh:
                return b"SJM_DIF" in fh.read(512)
        except Exception:
            return False

    def prepare(self, source: ImportSource) -> ImportPlan:
        groups = group_dif_files(source.list(_MAP_GLOB))
        maps: list[MapPlan] = []
        for key, files in groups.items():
            counts = {f: _vertex_count(source, f) for f in files}
            distinct = {c for c in counts.values() if c}
            issues = ["vertex counts differ across grouped files"] if len(distinct) > 1 else []
            scalar_fields = {}
            for f in files:
                field_name, kind = scalar_kind_for(parse_map_descriptor(f))
                scalar_fields[field_name] = kind
            maps.append(
                MapPlan(
                    map_name=key,
                    files=files,
                    part=parse_map_descriptor(files[0]).get("part"),
                    scalar_fields=scalar_fields,
                    n_vertices=next(iter(distinct), None),
                    issues=issues,
                )
            )

        wf_files = sorted({n for g in _WAVEFORM_GLOBS for n in source.list(g)})
        waveforms = WaveformPlan(
            files=wf_files,
            estimated_bytes=sum(source.size(n) for n in wf_files),
            include=False,  # opt-in
        )
        prov = _read_provenance(source)
        study = StudyPlan(
            study_name=prov.get("study_guid") or "ensite-study",
            vendor="ensite",
            provenance=prov,
            maps=maps,
            waveforms=waveforms,
        )
        return ImportPlan(studies=[study])

    def commit(self, plan: ImportPlan, source: ImportSource) -> list[Study]:
        studies: list[Study] = []
        for sp in plan.studies:
            study = Study(sp.study_name, vendor=sp.vendor, provenance=sp.provenance)
            src_tag = f"ensite/{sp.provenance.get('software_version', '?')}"
            for mp in sp.maps:
                if not mp.include:
                    continue
                items = [(f, parse_dif(source.open(f).read())[0]) for f in mp.files]
                try:
                    study.add_epmap(merge_dif_group(items, sp.study_name, src_tag))
                except GeometryMismatch:
                    for f, vol in items:  # geometry differs → keep separate
                        study.add_epmap(dif_to_epmap(vol, parse_map_descriptor(f), sp.study_name, src_tag))
            # plan.waveforms.include -> Phase 1.5 (WaveformStore); not yet built
            studies.append(study)
        return studies

    def parse(self, source: ImportSource) -> list[Study]:
        """Protocol convenience: prepare then commit with default selections."""
        return self.commit(self.prepare(source), source)


register_importer(EnsiteImporter())
