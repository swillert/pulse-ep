"""EnSite DxL row-wise, point/group-linked waveform exports.

These are distinct from the continuous ``t_dws`` tables: a row contains a
whole signal, with an explicit sample rate and zero-based sample columns.
Amplitude units are not inferred from the magnitudes of the stored values.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np

from pulse_ep.core.waveform import UNKNOWN_UNIT, Waveform


def iter_dxl_waveforms(data: bytes | str, name: str):
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    rows = list(csv.reader(io.StringIO(text)))
    rate = None
    exported_samples = None
    for row in rows:
        if row and row[0].strip().casefold() == "sample rate:" and len(row) > 1:
            rate = float(row[1])
        if row and row[0].strip().casefold() == "waveform samples exported:" and len(row) > 1:
            exported_samples = int(row[1])
    if exported_samples == 0:
        return  # explicit vendor declaration: this reference was not recorded
    if rate is None or not np.isfinite(rate) or rate <= 0:
        raise ValueError(f"{name}: missing/invalid DxL sample rate")
    header_index = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Trace"), None)
    if header_index is None:
        raise ValueError(f"{name}: no DxL Trace header")
    header = [c.strip() for c in rows[header_index]]
    columns = {c: i for i, c in enumerate(header)}
    first = columns.get("0")
    if first is None:
        raise ValueError(f"{name}: no zero-based sample columns")
    sample_columns = header[first:]
    if sample_columns and not sample_columns[-1]:
        sample_columns = sample_columns[:-1]
    if sample_columns != [str(i) for i in range(len(sample_columns))]:
        raise ValueError(f"{name}: non-contiguous sample columns")
    if exported_samples is not None and exported_samples != len(sample_columns):
        raise ValueError(f"{name}: sample count differs from declared number")
    stem = Path(name).stem.casefold()
    role = {
        "wave_rov": "bipolar",
        "wave_uni_distal": "unipolar_1",
        "wave_uni_proximal": "unipolar_2",
        "wave_refs": "reference",
        "wave_ref": "reference",
        "wave_refs2": "reference_2",
    }.get(stem, "ecg" if stem.startswith("wave_ecg") else "unknown")
    for number, row in enumerate(rows[header_index + 1 :], start=1):
        if row and row[0].strip() == "EOF":
            break
        if not row or not any(c.strip() for c in row):
            continue
        if len(row) < first + len(sample_columns):
            raise ValueError(f"{name}: truncated signal row {number}")

        def cell(key, row=row):
            j = columns.get(key)
            return row[j].strip() if j is not None and j < len(row) else ""

        start = float(cell("startTime (abs)"))
        samples = np.array(
            [float(x) if x.strip() else np.nan for x in row[first : first + len(sample_columns)]]
        )
        point_id = cell("(Point #)")
        # Reference rows identify a freeze group, not necessarily an individual point.
        if role.startswith("reference"):
            point_id = ""
        trace = cell("Trace")
        meta = {
            "format": "ensite_dxl",
            "signal_role": role,
            "point_id": point_id or None,
            "freeze_group": cell("Freeze Grp #"),
            "start_time": start,
            "time_unit": "s",
            "source_folder": str(Path(name).parent),
            "source_file": str(name),
        }
        tick = cell("rovTime (wave samples)")
        if tick:
            value = float(tick)
            if np.isfinite(value) and 0 <= value < len(samples):
                meta["map_sample_zero_based"] = value
        yield (
            number,
            Waveform(
                data=samples[:, None],
                channels=[trace],
                units=[UNKNOWN_UNIT],
                sample_rate=rate,
                signal_type="ecg" if role == "ecg" else "egm_" + role,
                time=np.arange(len(samples), dtype=float) / rate,
                meta=meta,
            ),
            point_id or None,
        )
