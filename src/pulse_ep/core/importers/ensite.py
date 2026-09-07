"""Abbott EnSite X (St. Jude) DIF decode.

Parses the ``SJM_DIF_5.0`` XML meshes (``Contact_Mapping_Model*.xml``,
``Model_Groups.xml``, ``difNNN.xml``) into vendor-neutral geometry +
scalar fields.

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
from pulse_ep.core.importers.lexicon import (
    ENSITE_DXL_CHANNELS,
    ENSITE_POINT_COLUMNS,
    ENSITE_POLARITY,
    ENSITE_POLARITY_CHANNELS,
    ENSITE_TIMESERIES_UNITS,
    resolve,
)
from pulse_ep.core.importers.plan import ImportPlan, MapPlan, StudyPlan, WaveformPlan
from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.measurement import MeasurementPoint
from pulse_ep.core.placed_point import ABLATION, ABLATION_PFA, LANDMARK, MARKER, PlacedPoint
from pulse_ep.core.scalar_field import (
    ANNOTATION_TIME,
    CONTACT_FORCE,
    UNKNOWN,
    VOLTAGE_BIPOLAR,
    field_name,
)
from pulse_ep.core.study import Study
from pulse_ep.core.waveform import UNKNOWN_UNIT, Waveform


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


def dif_volume_names(xml: bytes | str) -> list[str]:
    """The names of the volumes in a DIF file, without decoding their meshes.

    ``prepare`` has to describe an import without doing it, and the anatomy
    file is the largest in an export — a real one is 31 MB holding nine
    volumes: the endocardium, six wall-thickness shells, the channels and the
    fat infiltration. A reviewer told only "2 files" cannot tell that from a
    single chamber.

    Streamed on ``start`` events, so the vertex text is skipped rather than
    read into a tree: naming the nine costs a fraction of parsing them.
    """
    data = xml.encode() if isinstance(xml, str) else xml
    names: list[str] = []
    try:
        for _, element in etree.iterparse(io.BytesIO(data), events=("start",), tag="Volume"):
            name = element.get("name")
            if name:
                names.append(name.strip())
    except etree.XMLSyntaxError:
        return names  # a truncated file still names what it got to
    return names


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
        color_high_low = (
            (float(chl[0]), float(chl[1])) if chl is not None and chl.size >= 2 else None
        )

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
    "voltage",
    "remap",
    "premap",
    "vt",
    "stim",
    "lvstim",
    "rvstim",
    "deep",
    "pre",
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

    # The trailing suffix is authoritative (and typo-tolerant); the token scan
    # is the fallback for the rare export that carries it mid-name.
    _, polarity = split_polarity(stem)
    if polarity is None:
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


def scalar_kind_for(descriptor: dict) -> str:
    """The quantity a DIF map's ``Map_data`` holds.

    DIF contact-mapping models carry voltage; the polarity comes from the
    descriptor and is looked up in the lexicon, defaulting to bipolar when the
    filename says nothing. Activation/other map types would need value-range
    detection — a later refinement, not assumed here.
    """
    polarity = descriptor.get("polarity")
    kind = resolve(ENSITE_POLARITY, polarity) if polarity else UNKNOWN
    return VOLTAGE_BIPOLAR if kind == UNKNOWN else kind


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
        kind = scalar_kind_for(descriptor)
        epmap.register_scalar(
            field_name(kind),
            volume.map_data,
            kind=kind,
            status_mask=volume.status_mask,
            source=source,
        )
    return epmap


# --- bipolar / unipolar grouping -------------------------------------------

# ``bi?polar`` / ``uni?polar`` absorb the missing-letter typos seen in real
# exports (``VT-bpolar``); operators rename maps by hand, so the suffix cannot
# be assumed well-formed.
_POLARITY_SUFFIX = re.compile(
    r"[-_ ]?(?:(?P<bi>bi?polar|bipol|bi)|(?P<uni>uni?polar|unipol|uni))$", re.IGNORECASE
)


class GeometryMismatch(Exception):
    """Raised when maps grouped as one map do not share vertex geometry."""


def split_polarity(stem: str) -> tuple[str, str | None]:
    """Split a DIF filename stem into ``(base, polarity)``.

    The single place polarity is decoded, so grouping and
    :func:`parse_map_descriptor` can never disagree about a filename.
    """
    m = _POLARITY_SUFFIX.search(stem)
    if m is None:
        return stem, None
    return stem[: m.start()], "bipolar" if m.group("bi") else "unipolar"


def group_key(filename: str) -> str:
    """Descriptor minus polarity — the identity a bi/uni pair shares."""
    return split_polarity(Path(filename).stem)[0]


def group_dif_files(names: list[str]) -> dict[str, list[str]]:
    """Group DIF filenames by :func:`group_key` (bi+uni of one map together).

    Grouping is case-insensitive: the same map is exported as ``RVStimPre-uni``
    and ``RvStimPre-bi`` often enough that a case-sensitive key splits a pair.
    The dict key keeps the casing of the group's first file, so the map name
    stays the operator's spelling.
    """
    buckets: dict[str, list[str]] = {}
    for name in names:
        buckets.setdefault(group_key(name).casefold(), []).append(name)
    return {group_key(files[0]): files for files in (sorted(v) for v in buckets.values())}


def merge_dif_group(items: list[tuple[str, DifVolume]], study_name: str, source: str) -> EPMap:
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
        kind = scalar_kind_for(parse_map_descriptor(name))
        epmap.register_scalar(
            field_name(kind), vol.map_data, kind=kind, status_mask=vol.status_mask, source=source
        )
    return epmap


# --- waveforms -------------------------------------------------------------

_TIME_COLS = {"t_dws", "t_secs", "t_usecs", "t_ref"}


#: Respiration phase as the point cloud spells it -> the code stored in its
#: place. The column is text and a :class:`~pulse_ep.core.waveform.Waveform`
#: holds numbers, so it is encoded rather than dropped: which phase a point was
#: collected in is what makes two positions of the same wall differ.
POINT_CLOUD_RESPIRATION_CODES: dict[str, float] = {
    "UNKNOWN": 0.0,
    "EXPIRATION": 1.0,
    "INSPIRATION": 2.0,
}


def _wallclock_seconds(values) -> np.ndarray:
    """``HH:MM:SS.mmm`` -> seconds from the first sample.

    The point cloud timestamps on the wall clock while the rest of the family
    carries ``t_ref`` — "timepoint relative to first timepoint in seconds", in
    the export's own words. Converting here gives every stored window the same
    time axis.
    """
    parsed = pd.to_timedelta(pd.Series(values).astype(str).str.strip(), errors="coerce")
    seconds = parsed.dt.total_seconds().to_numpy(dtype=float)
    if seconds.size and np.isfinite(seconds).any():
        seconds = seconds - np.nanmin(seconds)
    return seconds


def parse_ensite_point_cloud(data: bytes | str, name: str = "") -> Waveform:
    """Parse an EnSite X ``Model_Point_Cloud.csv``.

    Every position the mapping catheter's electrodes reported while the
    anatomical model was being collected — on a real export 198 186 of them
    over two hours ten, in bursts of simultaneous samples because a
    multi-electrode catheter contributes several per frame. It is the one
    export in this family that spans the whole study rather than a segment,
    which is why its ``Export from Segment`` reads ``N/A``.

    It answers what no other file can: **how densely a chamber was actually
    sampled**, and therefore where a map rests on measurements and where on
    interpolation. The distance from these points to the fitted surface is a
    measure of the model's own quality.

    Two coordinate frames are stored side by side. ``trn_*`` is registered to
    the model — on the reference export a median 8.5 mm from the nearest vertex
    of the mapping mesh — while ``raw_*`` is the tracking frame before
    registration, some 360 mm away. Keeping both means the registration itself
    is recoverable from the pairs; it is recorded nowhere else in the export.
    """
    meta, df = parse_dws_table(data, marker="Time,", time_cols={"Time"})
    time = _wallclock_seconds(df["Time"]) if "Time" in df.columns else None

    channels: list[str] = []
    columns: list[np.ndarray] = []
    units: list[str] = []
    for column in df.columns:
        if column == "Time":
            continue
        if column == "respiration_phase":
            phase = df[column].astype(str).str.strip().str.upper()
            columns.append(phase.map(POINT_CLOUD_RESPIRATION_CODES).to_numpy(dtype=float))
        else:
            columns.append(df[column].to_numpy(dtype=float))
        channels.append(str(column))
        units.append(_point_cloud_unit(str(column)))

    return Waveform(
        data=np.column_stack(columns) if columns else np.empty((len(df), 0)),
        channels=channels,
        units=units,
        sample_rate=None,  # bursts of simultaneous samples, not a fixed rate
        signal_type=_signal_type(meta.get("Export Data Element", "") or name),
        time=time,
        meta={
            "segment": meta.get("Export from Segment"),
            "study_guid": meta.get("Export from Study"),
            "software_version": meta.get("Exported from Software Version"),
            "export_data_element": meta.get("Export Data Element"),
            "export_file_version": meta.get("Export File Version"),
            "field_scaling": meta.get("Field Scaling"),
            "dif_fusion": meta.get("DIF Fusion"),
            "respiration_phase_codes": POINT_CLOUD_RESPIRATION_CODES,
        },
    )


def _point_cloud_unit(column: str) -> str:
    """``trn_*`` is in the model's frame; ``raw_*`` is not, and says no scale.

    The transformed coordinates share the frame the mesh vertices are declared
    in, so millimetres is a fact about them. The raw ones are the tracking
    space before registration — the preamble notes ``Field Scaling: off`` and
    states no unit — so calling them millimetres because the numbers look
    similar would be the guess this field exists to prevent.
    """
    return "mm" if column.strip().lower().startswith("trn_") else UNKNOWN_UNIT


#: File-name markers of the per-timepoint family, all read by one parser.
_TIMESERIES_ELEMENTS = (
    "contact_force",
    "electrode_locations",
    "contact_index",
    "magnetic_location",
)

#: Read separately: its header is ``Time,`` and it spans the whole study.
_POINT_CLOUD_ELEMENT = "model_point_cloud"


def _signal_type(name: str) -> str:
    """The stored ``signal_type`` for an export, from its ``Export Data Element``.

    Electrograms keep the names they have always been stored under. Everything
    else takes the vendor's own element name, lowercased: ``Contact_Force_Raw``
    becomes ``contact_force_raw`` and ``Respiration_Compensated_Magnetic_Location``
    keeps its full name. That needs no table to maintain, and it keeps the
    processing stages apart — a listing that called three force windows
    ``contact_force`` would be useless, and the four magnetic variants are the
    same value computed four ways.
    """
    n = Path(name).stem.lower() if name else ""
    if "unipolar" in n and "magnetic" not in n:
        return "egm_unipolar"
    if "bipolar" in n and "magnetic" not in n:
        return "egm_bipolar"
    if "ecg" in n:
        return "ecg"
    if _POINT_CLOUD_ELEMENT in n or any(k in n for k in _TIMESERIES_ELEMENTS):
        return re.sub(r"[^a-z0-9]+", "_", n).strip("_")
    return ""


def parse_dws_table(
    data: bytes | str,
    marker: str = "t_dws,",
    time_cols: set[str] | None = None,
) -> tuple[dict, pd.DataFrame]:
    """Split an EnSite X per-timepoint export into ``(preamble, samples)``.

    Every one of them is built the same way: a metadata preamble of
    ``Key: value`` lines, optional legend blocks (data status bits, the
    ``channel,catheter name,electrode name`` table, a column glossary), then a
    header row starting ``t_dws,`` and the sample matrix under it.

    The header is found by that marker and never by counting lines or by
    taking the first comma-separated row — in
    ``Respiration_Compensated_Magnetic_Location`` the electrode table sits at
    line 149 and the glossary at 94, while the samples do not start until 234.

    ``marker`` and ``time_cols`` differ for the model point cloud: it is the
    one export in this family with its own header (``Time,``) and a single
    wall-clock time column instead of the four ``t_*`` ones.
    """
    time_cols = _TIME_COLS if time_cols is None else time_cols
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()

    meta: dict = {}
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith(marker):
            header_idx = i
            break
        s = line.strip()
        if s and ":" in s and not s.startswith(("Catheter[", "Electrode[")):
            key, val = s.split(":", 1)
            meta[key.strip()] = val.strip()
    if header_idx is None:
        raise ValueError(f"no sample-matrix header ({marker}...) found")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]

    # Every one of these files ends with a literal ``EOF`` line, which the CSV
    # reader turns into a row with a timestamp column and nothing else. Dropped
    # here rather than in each reader: it is a property of the format, and a
    # caller that missed it would store one all-NaN sample per window.
    values = [c for c in df.columns if c not in time_cols]
    if values:
        df = df[~df[values].isna().all(axis=1)]
    return meta, df


def _dws_start_time(df) -> float | None:
    """The first sample's time on the study clock, from ``t_secs``/``t_usecs``.

    The matrix carries ``t_ref`` relative to its own first sample, which says
    nothing about *when* the window was recorded. The absolute pair is right
    beside it in every one of these files and was being dropped — and it is
    what ties a per-segment window to the points acquired inside it.
    """
    if df.empty or "t_secs" not in df.columns or "t_usecs" not in df.columns:
        return None
    try:
        secs = float(df["t_secs"].iloc[0])
        usecs = float(df["t_usecs"].iloc[0])
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(secs) and np.isfinite(usecs)):
        return None
    return secs + usecs / 1e6


def _dws_time(df) -> tuple[np.ndarray | None, float | None]:
    """``t_ref`` as the time axis, and the rate implied by its spacing."""
    time = df["t_ref"].to_numpy(dtype=float) if "t_ref" in df.columns else None
    sample_rate = None
    if time is not None and time.size > 1:
        steps = np.diff(time)
        steps = steps[steps > 0]
        if steps.size:
            sample_rate = float(round(1.0 / float(np.median(steps))))
    return time, sample_rate


def parse_ensite_waveforms(data: bytes | str, name: str = "") -> Waveform:
    """Parse an EnSite ``EP_Catheter_*_Waveforms`` / ``ECG_*`` CSV.

    Each channel is a triplet ``X`` / ``X_ds`` / ``X_ps``; only the base ``X``
    column is the signal. See :func:`parse_dws_table` for the file's shape.
    """
    meta, df = parse_dws_table(data)

    signal_cols = [
        c for c in df.columns if c not in _TIME_COLS and not str(c).endswith(("_ds", "_ps"))
    ]
    signal = df[signal_cols].to_numpy(dtype=float)

    time, sample_rate = _dws_time(df)

    filters = {k: meta[k] for k in ("Highpass", "Lowpass", "Notch") if k in meta}
    return Waveform(
        data=signal,
        channels=[str(c) for c in signal_cols],
        sample_rate=sample_rate,
        signal_type=_signal_type(name or meta.get("Export Data Element", "")),
        # Not millivolts: this parser applies no gain, and the export declares
        # neither a unit nor a scale factor anywhere in its preamble — unlike
        # CARTO's, which carries one gain factor that carto_signal applies.
        # Whatever these numbers are, saying so is better than asserting mV.
        units=[UNKNOWN_UNIT] * len(signal_cols),
        time=time,
        meta={
            "segment": meta.get("Export from Segment"),
            "study_guid": meta.get("Export from Study"),
            "software_version": meta.get("Exported from Software Version"),
            "start_time": _dws_start_time(df),
            "filters": filters,
        },
    )


#: A position column: ``c12x`` -> channel 12, axis x. The file's own glossary
#: spells it ``c###x|y|z : channel ### x|y|z coordinate``.
_POSITION_COLUMN = re.compile(r"^c(\d+)([xyz])$", re.IGNORECASE)

#: A per-channel prefix (``c0_contactIndex``) or a per-sensor suffix
#: (``totalForce_0``). Both index the same quantity; neither is part of it.
_CHANNEL_PREFIX = re.compile(r"^c\d+_", re.IGNORECASE)
_SENSOR_SUFFIX = re.compile(r"_\d+$")

#: Header of the channel table that precedes the samples in the location,
#: contact-index and magnetic-location exports.
_CHANNEL_TABLE_HEADER = "channel,catheter name,electrode name"


def parse_channel_map(data: bytes | str) -> dict[str, dict]:
    """The ``channel,catheter name,electrode name,is visible`` table, by channel.

    This is the bridge between the numbered channels a signal export writes and
    the electrode labels a measurement point carries (``CS_1``, ``20A_1``) —
    stated by the export instead of inferred from the labels. It is a second
    table *inside* the file, above the sample matrix, so it is read separately
    from :func:`parse_dws_table`.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(_CHANNEL_TABLE_HEADER)), None)
    if start is None:
        return {}
    out: dict[str, dict] = {}
    for ln in lines[start + 1 :]:
        cells = [c.strip() for c in ln.split(",")]
        if not cells or not cells[0].isdigit():
            break  # the table ends where the numbering does
        entry = {"catheter": cells[1] if len(cells) > 1 else ""}
        if len(cells) > 2:
            entry["electrode"] = cells[2]
        if len(cells) > 3:
            entry["visible"] = cells[3] == "1"
        out[cells[0]] = entry
    return out


def timeseries_channel_unit(column: str) -> str:
    """The unit of one per-timepoint channel, or ``unknown``.

    Handles every column shape these exports use: a coordinate (``c12x``), a
    per-channel prefix (``c0_contactIndex``), a per-sensor suffix
    (``totalForce_0``, ``tx_1``), and the ``_ds`` / ``_ps`` status columns that
    accompany many of them.

    A status column never inherits its quantity's unit — ``c0_contactIndex_ds``
    is a bitfield, not an index. Only physical units are assigned. Quaternion
    components, contact indices and level codes are left ``unknown`` rather
    than given a "dimensionless" token: recording that a value has no unit is
    a distinction worth having, but it is not the one this field was added to
    make, and inventing vocabulary for it here would be premature.
    """
    name = column.strip()
    if name.endswith(("_ds", "_ps")):
        return UNKNOWN_UNIT
    if _POSITION_COLUMN.match(name):
        # Same coordinate frame as the mesh vertices, which the REST layer
        # already declares as mm. Not inferred from the column name.
        return "mm"
    base = _SENSOR_SUFFIX.sub("", _CHANNEL_PREFIX.sub("", name)).casefold()
    return ENSITE_TIMESERIES_UNITS.get(base, UNKNOWN_UNIT)


def parse_ensite_timeseries(data: bytes | str, name: str = "") -> Waveform:
    """Parse any EnSite X per-timepoint export into a :class:`Waveform`.

    Contact force, electrode locations, contact index and the four magnetic
    location variants are one family: a preamble, legend blocks, a
    ``t_dws`` header and a sample matrix (see :func:`parse_dws_table`). They
    differ only in which quantities their columns hold.

    Every non-time column is kept, status and message columns included: the
    legend that explains their bits is in the file's own preamble, and they are
    the only record of why a sample is unreliable. Raw column names are kept
    rather than rewritten to electrode labels, so that what is stored still
    matches what the export wrote; the mapping travels alongside in
    ``meta["channels"]`` for anyone who wants ``CS/D`` instead of ``c0``.
    """
    meta, df = parse_dws_table(data)
    channels = [c for c in df.columns if c not in _TIME_COLS]
    time, sample_rate = _dws_time(df)
    element = meta.get("Export Data Element", "")
    return Waveform(
        data=df[channels].to_numpy(dtype=float) if channels else np.empty((len(df), 0)),
        channels=[str(c) for c in channels],
        units=[timeseries_channel_unit(str(c)) for c in channels],
        sample_rate=sample_rate,
        signal_type=_signal_type(element or name),
        time=time,
        meta={
            "segment": meta.get("Export from Segment"),
            "study_guid": meta.get("Export from Study"),
            "software_version": meta.get("Exported from Software Version"),
            "export_data_element": element,
            "export_file_version": meta.get("Export File Version"),
            "start_time": _dws_start_time(df),
            "channels": parse_channel_map(data),
        },
    )


def _reader_for(name: str):
    """The parser for one per-timepoint export, chosen by its file name.

    Both read the same ``t_dws`` matrix; they differ in which columns are
    signal and where the units come from. Contact force keeps every column
    including the status ones and takes units from the lexicon; the waveform
    reader drops the ``_ds``/``_ps`` flag columns of each channel triplet.
    """
    stem = Path(name).name.casefold()
    if _POINT_CLOUD_ELEMENT in stem:
        return parse_ensite_point_cloud
    if any(k in stem for k in _TIMESERIES_ELEMENTS):
        return parse_ensite_timeseries
    return parse_ensite_waveforms


def iter_waveforms(study_plan, source: ImportSource):
    """Yield ``(key stem, waveform, point id, map name)`` for a plan's signals.

    EnSite X waveforms are per *segment*, so they belong to neither an acquired
    point nor a single map — both are ``None``, which is the shape the ingest
    path shares with CARTO, where they are not.
    """
    for name in study_plan.waveforms.files:
        yield (
            Path(name).stem,
            _reader_for(name)(source.open(name).read(), name=name),
            None,
            None,
        )


# --- measurement points (map_*_points.csv) ---------------------------------

#: Columns of the raw-archive ``map_*_points.csv``, in the order they are read.
#: The quantity each denotes comes from the lexicon, and its name from that.
_POINT_COLUMNS = ("pp", "unipoleMaxPP", "correctedLAT", "correlationCoefficient", "snr")

_MAP_PP_SENTINEL = 9000.0  # adjTime uses 10000 as "no annotation"


def _dxl_quantity(map_type: str) -> str:
    """The quantity a DxL ``Map type:`` denotes (e.g. ``CFEmean_bi`` -> cfe_mean).

    One export writes the *same* point set once per channel — same columns,
    same point ids, only the value column differs — so the channels merge back
    into one set of points carrying every measurement (:func:`_merge_point_sets`).

    ``PP`` is the one channel whose quantity depends on the polarity suffix
    rather than the channel token, so it is resolved against that lexicon.
    A channel neither table knows comes back :data:`UNKNOWN` and is imported
    under its raw column name — it must not inherit the voltage reading.

    Polarity is decoded by :func:`split_polarity` and nowhere else. This used
    to split on the last underscore itself, which is the arrangement that let
    grouping and the descriptor disagree about a filename once already.
    """
    channel, polarity = split_polarity(map_type)
    token = channel or map_type
    if token.strip().casefold() in ENSITE_POLARITY_CHANNELS:
        return resolve(ENSITE_POLARITY, polarity or "")
    return resolve(ENSITE_DXL_CHANNELS, token)


def _dxl_measurement_name(map_type: str, kind: str, value_col: str) -> str:
    """The name a DxL channel's measurement is stored under.

    ``PP`` carries its polarity in the *kind* — ``voltage_bipolar`` and
    ``voltage_unipolar`` are different quantities — so its name follows from
    the kind alone. Every other channel has a polarity-agnostic kind:
    ``CFEmean_bi`` and ``CFEmean_uni`` are one quantity measured on two
    signals, and both resolved to one name. Since a map's channels merge by
    point id, the unipolar file silently overwrote the bipolar one, and which
    survived depended on the order the files were parsed in.

    A bipolar channel keeps the bare name. That is what exports carry in
    practice, and suffixing it would rename the field in every study already
    imported, for a file nobody has yet seen. A polarity that is *not* bipolar
    is suffixed, so the two can no longer collide.
    """
    name = field_name(kind, value_col)
    channel, polarity = split_polarity(map_type)
    if (channel or map_type).strip().casefold() in ENSITE_POLARITY_CHANNELS:
        return name
    return f"{name}_uni" if polarity == "unipolar" else name


def dxl_map_name(data: bytes | str) -> str | None:
    """The operator's name for a map, from a DxL export's ``Map name:`` line.

    The DIF file names a map after its file — ``Contact_Mapping_Model`` for
    every one of them — while the point exports carry what the operator called
    it. The value is ``<model>\t<name>``: an export whose segments read
    ``VoXel<TAB>VT induction`` names its map ``VoXel<TAB>REMAP - SR``, the same
    shape with the same model in front. The part after the last tab is the name;
    the whole string is kept by the caller so nothing is invented away.

    ``None`` when the line is absent or holds no name, which leaves the caller
    with the file stem it had before.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()
    # ``Data starts in row,N`` is *not* the end of the preamble — in a real
    # export it sits at line 15 and ``Map name:`` at 17. It states where the
    # point table begins, and everything above that row is metadata.
    limit = len(lines)
    for line in lines[:80]:
        if line.lower().startswith("data starts in row") and "," in line:
            try:
                limit = int(line.split(",")[1])
            except ValueError:
                pass
            break
    for line in lines[: min(limit, 200)]:
        if line.lower().startswith("map name:"):
            raw = line.split(",", 1)[1].strip() if "," in line else ""
            name = raw.split("\t")[-1].strip()
            return name or None
    return None


def _value_column(header: list[str]) -> str | None:
    """The DxL value column — the one paired with a ``"<name> valid"`` sibling.

    Self-describing, so a channel this importer has never seen is still found
    without a lookup table of column names.
    """
    valid = {h[: -len(" valid")] for h in header if h.endswith(" valid")}
    return next((h for h in header if h in valid), None)


def parse_ensite_map_pp(data: bytes | str, name: str = "") -> list[MeasurementPoint]:
    """Parse a native structured ``Map_<channel>_*.csv`` (DxL point export).

    Skips the multi-section preamble via its ``Data starts in row,N`` marker,
    reads the point table, and maps: ``surface x/y/z`` -> position, the
    channel's value column (when its ``"<name> valid"`` sibling is set) ->
    the measurement named by the ``Map type`` (P-P -> voltage, with the
    polarity from the same header; LAT -> activation_time; CFE mean, Score,
    …), ``adjTime (ms)`` -> annotation_time, ``force (g)`` -> contact_force,
    ``roving x/y/z`` (labelled by ``Electrodes``) -> electrodes. Trailing
    variable "Rov Tick" columns are ignored, so parsing is done by hand.

    ``adjTime (ms)`` is deliberately *not* activation time: in real exports it
    is the annotation window offset and is often constant across every point
    of the study. A map's activation time is the ``LAT`` channel's own column.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()

    data_row = None
    map_type = ""
    for line in lines[:80]:
        low = line.lower()
        if low.startswith("data starts in row"):
            try:
                data_row = int(line.split(",")[1])
            except (IndexError, ValueError):
                pass
        elif low.startswith("map type:"):
            map_type = line.split(",", 1)[1].strip()
    if data_row is None:
        raise ValueError("no 'Data starts in row,N' marker found")

    header = [h.strip() for h in lines[data_row - 1].split(",")]
    col = {name: i for i, name in enumerate(header)}

    value_col = _value_column(header) or "P-P"
    kind = _dxl_quantity(map_type)
    # An unrecognised channel keeps the export's own column name, so it is
    # imported and visible rather than dropped or mislabelled as voltage.
    measurement = _dxl_measurement_name(map_type, kind, value_col)

    def num(fields, name):
        j = col.get(name)
        if j is None or j >= len(fields):
            return None
        try:
            return float(fields[j])
        except ValueError:
            return None

    points: list[MeasurementPoint] = []
    for i, line in enumerate(lines[data_row:]):
        if not line.strip():
            continue
        f = line.split(",")
        sx, sy, sz = num(f, "surface x"), num(f, "surface y"), num(f, "surface z")
        if sx is None or sy is None or sz is None:
            continue
        point = MeasurementPoint(position=np.array([sx, sy, sz], dtype=float), index=i)

        pid = col.get("(Point #)")
        if pid is not None and pid < len(f):
            point.source_id = f[pid].strip()

        value = num(f, value_col)
        valid_col = col.get(f"{value_col} valid")
        is_valid = valid_col is None or (
            valid_col < len(f) and f[valid_col].strip() in ("1", "1.0")
        )
        if value is not None and is_valid:
            point.add(measurement, value, kind)

        annot = num(f, "adjTime (ms)")
        if annot is not None and abs(annot) < _MAP_PP_SENTINEL:
            point.add("annotation_time", annot, ANNOTATION_TIME, "ms")

        # When this point was acquired, on the study clock. It is the one thing
        # that ties a point to the per-timepoint exports — contact force and
        # electrode locations come per *segment*, so without an absolute time
        # nothing can say which window covers which point. CARTO records the
        # same thing under the same key; the difference is that a CARTO window
        # belongs to a point outright and an EnSite X one has to be found.
        ref_abs = num(f, "refTime (abs)")
        if ref_abs is not None and ref_abs > 0:
            point.annotations["start_time"] = ref_abs

        force = num(f, "force (g)")
        if force is not None and force >= 0:
            point.add("contact_force", force, CONTACT_FORCE, "g")

        rx, ry, rz = num(f, "roving x"), num(f, "roving y"), num(f, "roving z")
        if rx is not None and ry is not None and rz is not None:
            elabel = f[col["Electrodes"]].strip() if "Electrodes" in col else ""
            point.electrodes[elabel or "rov"] = np.array([rx, ry, rz], dtype=float)

        points.append(point)
    return points


def parse_ensite_points(data: bytes | str, name: str = "") -> list[MeasurementPoint]:
    """Parse a raw-archive-derived ``map_*_points.csv`` into vendor-neutral points.

    This is the rich per-point table assembled from the raw ``dws.db`` archive
    (see ``export_ensite_map_points.py``) — a Phase-3 source. The native
    structured-export equivalent is :func:`parse_ensite_map_pp`.

    Maps pp / unipoleMaxPP / correctedLAT / correlationCoefficient / snr / force
    + locChA/B/C electrodes onto an open ``measurements`` dict.
    ``correlationCoefficient`` is imported neutrally as ``correlation`` (its
    clinical meaning is decided downstream). ``force == -1`` (no sensor) is dropped.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    df = pd.read_csv(io.StringIO(text))
    cols = set(df.columns)

    points: list[MeasurementPoint] = []
    for i, row in df.iterrows():
        point = MeasurementPoint(
            position=np.array([row["x"], row["y"], row["z"]], dtype=float), index=int(i)
        )
        for col in _POINT_COLUMNS:
            if col in cols and pd.notna(row[col]):
                kind = resolve(ENSITE_POINT_COLUMNS, col)
                point.add(field_name(kind, col), float(row[col]), kind)
        if "force" in cols and pd.notna(row["force"]) and float(row["force"]) >= 0:
            point.add("contact_force", float(row["force"]), CONTACT_FORCE, "g")
        for label in ("A", "B", "C"):
            axis_cols = [f"locCh{label}_{ax}" for ax in "xyz"]
            if cols.issuperset(axis_cols):
                point.electrodes[label] = np.array([row[c] for c in axis_cols], dtype=float)
        points.append(point)
    return points


# --- placed points (AutoMarks / Lesions / Labels) --------------------------


def _element_df(data: bytes | str, header_prefix: str):
    """Read ONE section of an 'Export Data Element' CSV from its header row.

    These files can hold several sections, each with its own header (e.g.
    AutoMark_Data has a NavX/power section then an EKG section) — so the block
    stops at a blank line or the next section's header.
    """
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    lines = text.splitlines()
    hi = next((i for i, line in enumerate(lines) if line.startswith(header_prefix)), None)
    if hi is None:
        return None
    block = [lines[hi]]
    for line in lines[hi + 1 :]:
        if not line.strip() or line.startswith(header_prefix):
            break
        block.append(line)
    # index_col=False: data rows often have a trailing empty field (one more
    # column than the header) — without this pandas shifts everything by one.
    df = pd.read_csv(io.StringIO("\n".join(block)), index_col=False)
    return df.dropna(how="all")


def parse_ensite_automarks(data: bytes | str, name: str = "") -> list[PlacedPoint]:
    """Parse ``AutoMark_Data.csv`` into ablation :class:`PlacedPoint`s.

    Position from the NavX ABL-D electrode; ablation power / episode / lesion
    id go into open attributes.
    """
    df = _element_df(data, "RF Episode,")
    if df is None:
        return []
    xc, yc, zc = "NavX ABL-D X (mm)", "NavX ABL-D Y (mm)", "NavX ABL-D Z (mm)"
    if xc not in df.columns:
        return []
    power_col = next((c for c in df.columns if "Power" in str(c)), None)

    points: list[PlacedPoint] = []
    for _, r in df.iterrows():
        if pd.isna(r[xc]):
            continue
        attrs: dict = {}
        if power_col and pd.notna(r[power_col]):
            attrs["power"] = float(r[power_col])
        for csv_col, key in (("RF Episode", "rf_episode"), ("Lesion ID", "lesion_id")):
            if csv_col in df.columns and pd.notna(r[csv_col]):
                attrs[key] = r[csv_col]
        points.append(
            PlacedPoint(
                type=ABLATION,
                position=np.array([r[xc], r[yc], r[zc]], dtype=float),
                source_id=str(r["Lesion ID"]) if "Lesion ID" in df.columns else None,
                attributes=attrs,
            )
        )
    return points


def parse_ensite_markers(data: bytes | str, point_type: str = MARKER) -> list[PlacedPoint]:
    """Parse a ``Lesions.csv`` / ``Labels.csv`` (Text,Type,Surface,x,y,z,...).

    Used for markers (``Lesions`` -> :data:`MARKER`) and landmarks
    (``Labels`` -> :data:`LANDMARK`); the file's own ``Type`` column, colour,
    diameter and annotation become open attributes.
    """
    df = _element_df(data, "Text,Type,")
    if df is None:
        return []
    points: list[PlacedPoint] = []
    for _, r in df.iterrows():
        if pd.isna(r.get("x")):
            continue
        attrs: dict = {}
        for csv_col, key in (
            ("Type", "marker_type"),
            ("Diameter", "diameter"),
            ("Annotation", "annotation"),
        ):
            if csv_col in df.columns and pd.notna(r[csv_col]):
                attrs[key] = r[csv_col]
        if {"R", "G", "B"}.issubset(df.columns):
            attrs["color"] = [int(r["R"]), int(r["G"]), int(r["B"])]
        text = str(r["Text"]) if "Text" in df.columns and pd.notna(r["Text"]) else None
        points.append(
            PlacedPoint(
                type=point_type,
                position=np.array([r["x"], r["y"], r["z"]], dtype=float),
                label=text,
                attributes=attrs,
                source_id=text,
            )
        )
    return points


def parse_ensite_labels(data: bytes | str, name: str = "") -> list[PlacedPoint]:
    """Parse ``Labels.csv`` into landmark :class:`PlacedPoint`s."""
    return parse_ensite_markers(data, point_type=LANDMARK)


def parse_ensite_duo_automarks(data: bytes | str, name: str = "") -> list[PlacedPoint]:
    """Parse ``Duo_AutoMarksSummaryList_VoXel.csv`` into PFA ablation points.

    Position from AutoMark Location X/Y/Z; burst counts, force, therapy setting
    and duration become open attributes.
    """
    # the specific data header (a "t_dws,<description>" legend line precedes it)
    df = _element_df(data, "t_dws,t_secs,")
    if df is None:
        return []
    xc, yc, zc = "AutoMark Location X", "AutoMark Location Y", "AutoMark Location Z"
    if xc not in df.columns:
        return []
    attr_cols = (
        ("Actual Burst Count", "actual_burst_count"),
        ("Expected Burst Count", "expected_burst_count"),
        ("Average Force", "avg_force"),
        ("Max Force", "max_force"),
        ("Therapy Setting", "therapy_setting"),
        ("Duration", "duration"),
    )
    points: list[PlacedPoint] = []
    for _, r in df.iterrows():
        if pd.isna(r[xc]):
            continue
        attrs = {key: r[c] for c, key in attr_cols if c in df.columns and pd.notna(r[c])}
        points.append(
            PlacedPoint(
                type=ABLATION_PFA,
                position=np.array([r[xc], r[yc], r[zc]], dtype=float),
                source_id=str(r["ID"]) if "ID" in df.columns else None,
                attributes=attrs,
            )
        )
    return points


_PLACED_GLOBS = (
    "*AutoMark_Data.csv",
    "*Duo_AutoMarksSummaryList*.csv",
    "*Lesions.csv",
    "*Labels.csv",
)


def _parse_placed_points(source: ImportSource, files: list[str]) -> list[PlacedPoint]:
    """Dispatch each placed-point file to its parser by filename."""
    points: list[PlacedPoint] = []
    for f in files:
        base = Path(f).name.lower()
        data = source.open(f).read()
        if "duo_automark" in base:
            points += parse_ensite_duo_automarks(data, f)
        elif "automark_data" in base:
            points += parse_ensite_automarks(data, f)
        elif "lesions" in base:
            points += parse_ensite_markers(data)
        elif "labels" in base:
            points += parse_ensite_labels(data, f)
    return points


# --- vendor importer (prepare / commit over an ImportSource) ---------------

_MAP_GLOB = "*Contact_Mapping_Model*.xml"
# Every DxL channel of a map (Map_PP_bi, Map_LAT_bi, Map_Score_bi, …), not just
# P-P: they describe the same points, so each adds a measurement to that set.
_POINTS_GLOB = "*Map_*.csv"
# Anatomy arrives in two shapes: the chamber shells of ``Model_Groups.xml``,
# and the numbered ``difNNN.xml`` bundles that carry CT-segmentation volumes
# (endocardium, wall-thickness shells, channels, fat infiltration).
_ANATOMY_GLOBS = ("*Model_Groups*.xml", "*dif[0-9][0-9][0-9].xml")
# Two naming schemes turn up in the wild for the same thing: one export
# writes ``ECG_Waveforms_Raw.csv`` / ``EP_Catheter_Bipolar_Waveforms_*.csv``,
# another writes ``Wave_rov.csv`` / ``Wave_uni_distal.csv``. Matching only the
# first reported "0 waveform files" for an export that was nothing but
# waveforms.
#: Per-timepoint signal exports. All share the ``t_dws`` sample-matrix shape
#: and go into the same Parquet store; ``_reader_for`` picks the parser.
_WAVEFORM_GLOBS = (
    "*Waveforms*.csv",
    "*ECG*.csv",
    "*Wave_*.csv",
    "*Contact_Force_*.csv",
    "*Electrode_Locations*.csv",
    "*Contact_Index*.csv",
    "*Magnetic_Location*.csv",
    "*Model_Point_Cloud*.csv",
)
_VERT_RE = re.compile(rb'<Vertices number="(\d+)"')


def _list_any(source: ImportSource, globs: tuple[str, ...]) -> list[str]:
    """Sorted union of the members matching any of ``globs``."""
    return sorted({n for g in globs for n in source.list(g)})


def _vertex_count(source: ImportSource, name: str) -> int | None:
    """Cheap header scan for the vertex count (no full parse)."""
    with source.open(name) as fh:
        head = fh.read(16384)
    m = _VERT_RE.search(head)
    return int(m.group(1)) if m else None


def _is_dxl_points_table(source: ImportSource, name: str) -> bool:
    """Cheap preamble check — a DxL point table, not some other ``Map_*.csv``.

    Keeps an unrelated file matching the glob from reaching the parser (which
    would raise and abort the whole study import).
    """
    try:
        with source.open(name) as fh:
            head = fh.read(4096).decode("utf-8", "ignore").lower()
    except Exception:
        return False
    return "data starts in row" in head and "map type:" in head


def _operator_map_name(source: ImportSource, points_files: list[str]) -> str | None:
    """The map's name as the system showed it, from its DxL point exports.

    Only the preamble of one file is needed, so this stays as cheap as the rest
    of ``prepare``. ``None`` when the channels disagree or say nothing — a map
    has one name or none, and picking one of two would be a guess.
    """
    names = set()
    for pf in points_files:
        try:
            name = dxl_map_name(source.open(pf).read(65536))
        except (OSError, ValueError):
            continue
        if name:
            names.add(name)
    return names.pop() if len(names) == 1 else None


def _anatomy_volume_names(source: ImportSource, files: list[str]) -> list[str]:
    """Every volume the anatomy files hold, for the reviewer to see.

    Read with :func:`dif_volume_names`, which skips the vertex text — on a real
    31 MB anatomy file naming its nine volumes takes a fourteenth of the time
    decoding them would.
    """
    names: list[str] = []
    for f in files:
        try:
            names.extend(dif_volume_names(source.open(f).read()))
        except (OSError, ValueError):
            continue  # a file that cannot be read is reported by the import, not here
    return names


def _points_files_for(source: ImportSource, map_files: list[str]) -> list[str]:
    """DxL point tables of a map's DIF files (in a ``Contact_Mapping/`` subdir)."""
    dirs = {str(Path(f).parent) for f in map_files}
    return sorted(
        pp
        for pp in source.list(_POINTS_GLOB)
        if str(Path(pp).parent.parent) in dirs and _is_dxl_points_table(source, pp)
    )


def _merge_point_sets(point_sets: list[list[MeasurementPoint]]) -> list[MeasurementPoint]:
    """Merge bi/uni/omni Map_PP point sets by point id (shared acquisition points)."""
    merged: dict[str, MeasurementPoint] = {}
    order: list[str] = []
    for points in point_sets:
        for p in points:
            key = p.source_id if p.source_id is not None else f"_{len(order)}"
            if key not in merged:
                merged[key] = p
                order.append(key)
            else:
                merged[key].measurements.update(p.measurements)
                merged[key].electrodes.update(p.electrodes)
    return [merged[k] for k in order]


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
    """Vendor importer for Abbott EnSite X (St. Jude) DIF exports."""

    name = "ensite"

    def sniff(self, source: ImportSource) -> bool:
        difs = source.list(_MAP_GLOB) or _list_any(source, _ANATOMY_GLOBS)
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
                kind = scalar_kind_for(parse_map_descriptor(f))
                scalar_fields[field_name(kind)] = kind
            points_files = _points_files_for(source, files)
            maps.append(
                MapPlan(
                    # What the operator called it, when the point exports say —
                    # otherwise the file stem, which is Contact_Mapping_Model
                    # for every map in the export and tells a reviewer nothing.
                    map_name=_operator_map_name(source, points_files) or key,
                    files=files,
                    part=parse_map_descriptor(files[0]).get("part"),
                    scalar_fields=scalar_fields,
                    n_vertices=next(iter(distinct), None),
                    points_files=points_files,
                    issues=issues,
                )
            )

        wf_files = _list_any(source, _WAVEFORM_GLOBS)
        waveforms = WaveformPlan(
            files=wf_files,
            estimated_bytes=sum(source.size(n) for n in wf_files),
            include=False,  # opt-in
        )
        prov = _read_provenance(source)
        placed_files = _list_any(source, _PLACED_GLOBS)
        anatomy_files = _list_any(source, _ANATOMY_GLOBS)
        study = StudyPlan(
            study_name=prov.get("study_guid") or "ensite-study",
            vendor="ensite",
            provenance=prov,
            maps=maps,
            waveforms=waveforms,
            placed_point_files=placed_files,
            anatomy_files=anatomy_files,
            anatomy_volumes=_anatomy_volume_names(source, anatomy_files),
        )
        issues: list[str] = []
        if not maps and not anatomy_files:
            # A partial export — point tables and waveforms without a single
            # mesh — used to import as an empty study and report success. Say
            # what is missing instead, so nobody concludes the data is in.
            have = []
            if wf_files:
                have.append(f"{len(wf_files)} waveform files")
            if placed_files:
                have.append(f"{len(placed_files)} placed-point files")
            found = ", ".join(have) or "no recognised data"
            issues.append(
                "no geometry in this export (no DIF model, no anatomy) — "
                f"nothing can be imported as a map; found {found}"
            )
        return ImportPlan(studies=[study], issues=issues)

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
                    epmap = merge_dif_group(items, sp.study_name, src_tag)
                    # The plan's name wins: it is the operator's, and a
                    # reviewer may have corrected it. The file stem is kept so
                    # a map can still be traced back to what it came from.
                    if mp.map_name and mp.map_name != epmap.map_name:
                        epmap.attributes.setdefault("source_stem", epmap.map_name)
                        epmap.map_name = mp.map_name
                    if mp.include_points and mp.points_files:
                        epmap.measurement_points = _merge_point_sets(
                            [
                                parse_ensite_map_pp(source.open(pf).read(), name=pf)
                                for pf in mp.points_files
                            ]
                        )
                    study.add_epmap(epmap)
                except GeometryMismatch:
                    for f, vol in items:  # geometry differs → keep separate
                        study.add_epmap(
                            dif_to_epmap(vol, parse_map_descriptor(f), sp.study_name, src_tag)
                        )
            if sp.include_placed_points and sp.placed_point_files:
                study.placed_points = _parse_placed_points(source, sp.placed_point_files)
            if sp.include_anatomy and sp.anatomy_files:
                for af in sp.anatomy_files:
                    for vol in parse_dif(source.open(af).read()):
                        study.add_epmap(
                            EPMap(
                                map_name=f"Anatomy: {vol.name}",
                                study_name=sp.study_name,
                                vertices=vol.vertices,
                                triangles=vol.triangles,
                                normals=vol.normals,
                                attributes={"kind": "anatomy", "chamber": vol.name},
                            )
                        )
            # plan.waveforms.include -> Phase 1.5 (WaveformStore); not yet built
            studies.append(study)
        return studies

    def parse(self, source: ImportSource) -> list[Study]:
        """Protocol convenience: prepare then commit with default selections."""
        return self.commit(self.prepare(source), source)


register_importer(EnsiteImporter())
