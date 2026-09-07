"""CARTO 3 signal exports — the per-point ECG files.

A CARTO export writes one ``*_ECG_Export_<timestamp>.txt`` per acquired
point: a fixed 2.5 s window of every recorded channel (surface leads,
coronary-sinus and mapping electrodes, derived bipoles), sampled at 1 kHz and
stored as raw integers with one gain factor in the header.

These were never imported — the note in ``point_importer`` said "too large for
DB storage", which was true of the relational DB and irrelevant to the
:class:`~pulse_ep.core.waveform.WaveformStore` that has existed since. They
are opt-in for the same reason EnSiteX waveforms are: a real export carries
one such file per point and they dwarf everything else in it.

The point XML says which channels a point was *annotated* on
(``UnipolarMappingChannel`` / ``BipolarMappingChannel`` / ``ReferenceChannel``)
and where its annotations sit in the window. That is what makes a stored
window usable rather than 78 anonymous traces, so it travels with the
waveform as metadata.

**A window belongs to several points.** A multi-electrode catheter acquires
many points from one 2.5 s recording, and each of them references the same
file: in the reference export, 1934 points share 699 windows, 84 % of them in
groups of up to ten. So the samples are stored once per window and the points
that were taken from it all point at that one copy.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from lxml import etree

from pulse_ep.core.importers.source import ImportSource
from pulse_ep.core.waveform import Waveform

#: CARTO records at 1 kHz. The export carries no sample-rate field — the only
#: statement of it is the file layout (2500 samples per 2.5 s window), so it
#: is recorded as a constant here rather than silently inferred per file.
CARTO_SAMPLE_RATE_HZ = 1000.0

#: ``*_ECG_Export_<start timestamp>.txt`` — the window's first sample, in the
#: study's own millisecond clock. The same number appears in the point XML
#: (``Annotations/@StartTime``), which is what links a file back to its point.
_ECG_FILE_RE = re.compile(r"_ECG_Export_(\d+)\.txt$", re.IGNORECASE)

#: ``M1(1)`` / ``CS1-CS2(101)`` — channel label plus CARTO's channel id.
_CHANNEL_RE = re.compile(r"^(?P<name>.+?)\((?P<id>\d+)\)$")

_GAIN_RE = re.compile(r"gain\)?\s*=\s*([0-9.eE+-]+)")

_ECG_GLOB = "*_ECG_Export_*.txt"


def ecg_files(source: ImportSource) -> list[str]:
    """Every per-point ECG export in ``source``."""
    return sorted(source.list(_ECG_GLOB))


def ecg_start_time(name: str) -> int | None:
    """The window start timestamp encoded in an ECG export's filename."""
    m = _ECG_FILE_RE.search(Path(name).name)
    return int(m.group(1)) if m else None


def _split_channel(token: str) -> tuple[str, int | None]:
    m = _CHANNEL_RE.match(token)
    if m is None:
        return token, None
    return m.group("name"), int(m.group("id"))


def parse_carto_ecg_export(data: bytes | str, name: str = "", context: list[dict] | None = None):
    """Parse one ``*_ECG_Export_*.txt`` into a :class:`Waveform`.

    Layout::

        ECG_Export_4.1
        Raw ECG to MV (gain) = 0.003000
        M1(1)   M2(2)   ...   CS1-CS2(101)   ...
        -2      18      ...   14             ...

    Samples are raw integers; the gain converts them to millivolts, and is
    applied here so a stored waveform is in a physical unit rather than in
    whatever the amplifier happened to count in. The ``(id)`` suffix of each
    channel is CARTO's channel number — kept in ``meta`` because the point XML
    references channels by *name*, but the voltages table by id.

    ``context`` is the list of points acquired in this window (see
    :func:`point_index`), where they are known.
    """
    text = data.decode("latin-1", "replace") if isinstance(data, bytes) else data
    lines = text.splitlines()
    if len(lines) < 4:
        raise ValueError(f"{name or 'ECG export'}: too short to be an ECG export")

    version = lines[0].strip()
    if not version.upper().startswith("ECG_EXPORT"):
        raise ValueError(f"{name or 'file'}: not a CARTO ECG export (got {version!r})")

    gain_match = _GAIN_RE.search(lines[1])
    # No gain line is a format we have not seen; keeping the raw counts and
    # saying so beats inventing a scale factor for clinical voltages.
    gain = float(gain_match.group(1)) if gain_match else 1.0

    header = [_split_channel(tok) for tok in lines[2].split()]
    channels = [n for n, _ in header]
    channel_ids = {n: i for n, i in header if i is not None}
    if not channels:
        raise ValueError(f"{name or 'ECG export'}: no channels in header")

    rows = [line.split() for line in lines[3:] if line.strip()]
    # A truncated final row (an export interrupted mid-write) is dropped
    # rather than padded: a short row would silently shift every channel.
    samples = np.array([r for r in rows if len(r) == len(channels)], dtype=float)
    if samples.size == 0:
        samples = np.empty((0, len(channels)))
    samples *= gain

    start = ecg_start_time(name)
    time = None
    if start is not None:
        # absolute study-clock milliseconds, so windows from different points
        # line up on one axis without re-deriving the offset at every read
        time = start + np.arange(len(samples), dtype=float)

    meta = {
        "export_version": version,
        "gain_mv": gain,
        "start_time": start,
        "channel_ids": channel_ids,
        "source_file": Path(name).name if name else None,
    }
    if context:
        # every point acquired in this window, each with the channels it was
        # annotated on and where its annotations sit
        meta["points"] = [
            {
                "point_id": info.get("point_id"),
                "mapping_channels": info.get("channels"),
                "annotations": info.get("annotations"),
            }
            for info in context
        ]
    return Waveform(
        data=samples,
        channels=channels,
        sample_rate=CARTO_SAMPLE_RATE_HZ,
        # a CARTO window is a mixed set — surface leads next to intracardiac
        # uni- and bipoles — so the per-channel type lives in the names, not
        # in one label for the file
        signal_type="ecg",
        time=time,
        meta=meta,
    )


def parse_point_export(data: bytes | str, name: str = "") -> dict | None:
    """The signal-relevant part of a ``P<n>_Point_Export.xml``.

    Returns ``None`` for an XML that is not a point export, so the caller can
    sweep a whole export directory without classifying files first.
    """
    raw = data if isinstance(data, bytes) else data.encode("utf-8", "replace")
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return None
    if root.tag != "Point":
        return None

    ecg = root.find("ECG")
    if ecg is None:
        return None

    annotations = root.find("Annotations")
    woi = root.find("WOI")

    def _int(element, attr):
        if element is None:
            return None
        value = element.get(attr)
        return int(float(value)) if value not in (None, "") else None

    return {
        "point_id": root.get("ID"),
        "ecg_file": ecg.get("FileName"),
        "channels": {
            "unipolar": ecg.get("UnipolarMappingChannel"),
            "bipolar": ecg.get("BipolarMappingChannel"),
            "reference": ecg.get("ReferenceChannel"),
        },
        "annotations": {
            "start_time": _int(annotations, "StartTime"),
            "reference": _int(annotations, "Reference_Annotation"),
            "map": _int(annotations, "Map_Annotation"),
            "woi_from": _int(woi, "From"),
            "woi_to": _int(woi, "To"),
        },
        "source_file": Path(name).name if name else None,
    }


def point_index(source: ImportSource) -> dict[str, list[dict]]:
    """Map each ECG export filename to **all** points acquired in that window.

    An export names its ECG files by timestamp, so nothing in a file itself
    says which points it belongs to or which of its 78 channels each was
    annotated on — only the point XMLs do. The XMLs are ~2 kB each, so
    building the whole index costs one cheap pass.

    Keyed to a list, not a single point: a multi-electrode catheter takes up
    to ten points from one window, and keeping only the last of them would
    leave most points of a real study looking as though no signal was
    recorded for them.
    """
    index: dict[str, list[dict]] = {}
    for name in source.list("*_Point_Export.xml"):
        try:
            info = parse_point_export(source.open(name).read(), name=name)
        except OSError:
            continue
        if info and info.get("ecg_file"):
            index.setdefault(Path(info["ecg_file"]).name, []).append(info)
    for points in index.values():
        points.sort(key=lambda i: _point_sort_key(i.get("point_id")))
    return index


def _point_sort_key(point_id):
    """Point ids are numbers written as text — ``"9"`` before ``"10"``."""
    try:
        return (0, int(point_id))
    except (TypeError, ValueError):
        return (1, str(point_id))


def map_name_for(name: str) -> str | None:
    """The map an ECG export belongs to: ``<map name>_ECG_Export_<ts>.txt``."""
    base = Path(name).name
    head = _ECG_FILE_RE.split(base)[0]
    return head or None


def iter_waveforms(
    study_plan, source: ImportSource
) -> Iterator[tuple[str, Waveform, str | None, str | None]]:
    """Yield ``(key stem, waveform, point id, map name)`` for a plan's ECG files.

    One yield **per point**, all sharing the window's key: the ingest path
    stores the samples once and gives every point acquired in that window its
    own reference to them, so "the signal at point 37" resolves whether or not
    point 37 happened to be the last one written to that file.
    """
    index = point_index(source)
    for name in study_plan.waveforms.files:
        points = index.get(Path(name).name) or []
        wave = parse_carto_ecg_export(source.open(name).read(), name=name, context=points)
        map_name = map_name_for(name)
        wave.meta["map_name"] = map_name
        stem = Path(name).stem
        if not points:
            yield stem, wave, None, map_name
            continue
        for info in points:
            yield stem, wave, info.get("point_id"), map_name
