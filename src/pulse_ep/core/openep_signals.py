"""Point-aligned signal arrays for OpenEP; selection uses recorded identities.

No resampling, channel substitution, or voltage calibration is implicit.
Different sampling rates cannot share OpenEP's single sampleFrequency.
"""

from __future__ import annotations

import re

import numpy as np

ECG_LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")


def _key(name):
    return re.sub(r"\(\d+\)$", "", str(name or "")).strip().casefold()


def _channel(wave, name):
    hits = [i for i, label in enumerate(wave.channels) if _key(label) == _key(name)]
    return hits[0] if name and len(hits) == 1 else None


def _unipoles(bipolar, unipolar):
    parts = str(bipolar or "").split("-")
    if len(parts) != 2:
        return [unipolar, None]
    first, second = parts
    if second.isdigit():
        second = re.sub(r"\d+$", second, first)
    return [unipolar or first, second]


def _bindings(point, windows, map_name):
    candidates = {}
    for wave in windows:
        meta = wave.meta
        if meta.get("map_name") and meta["map_name"] != map_name:
            continue
        if meta.get("format") == "ensite_dxl":
            annotations = point.annotations or {}
            if meta.get("source_folder") != annotations.get("source_folder"):
                continue
            role = meta["signal_role"]
            if role.startswith("reference"):
                matched = bool(meta.get("freeze_group")) and meta[
                    "freeze_group"
                ] == annotations.get("freeze_group")
            else:
                matched = str(meta.get("point_id")) == str(point.source_id)
            if matched and role != "unknown":
                if role == "ecg":
                    role = "ecg:" + _key(wave.channels[0])
                candidates.setdefault(role, []).append((wave, 0))
            continue
        # CARTO windows carry explicit channel choices for each point, even
        # when several points share the same stored window.
        for context in meta.get("points", []):
            if str(context.get("point_id")) != str(point.source_id):
                continue
            channels = context.get("mapping_channels") or {}
            uni = _unipoles(channels.get("bipolar"), channels.get("unipolar"))
            names = {
                "bipolar": channels.get("bipolar"),
                "reference": channels.get("reference"),
                "unipolar_1": uni[0],
                "unipolar_2": uni[1],
            }
            for role, name in names.items():
                column = _channel(wave, name)
                if column is not None:
                    candidates.setdefault(role, []).append((wave, column))
    # Duplicated DB references to one window are resolved by the loader.
    # Multiple distinct candidates are ambiguous and must not pick a winner.
    return {
        role: entries[0] for role, entries in candidates.items() if len(entries) == 1
    }, candidates


def signal_arrays(epmap, windows, ecg_channels=None, scale_to_mv=None):
    if scale_to_mv is not None and (not np.isfinite(scale_to_mv) or scale_to_mv <= 0):
        raise ValueError("signal_scale_to_mv must be finite and positive")
    points = list(epmap.measurement_points or [])
    bindings, ambiguous = [], 0
    for point in points:
        selected, candidates = _bindings(point, windows, epmap.map_name)
        bindings.append(selected)
        ambiguous += sum(len(entries) > 1 for entries in candidates.values())
    rates = {
        float(w.sample_rate)
        for selected in bindings
        for w, _ in selected.values()
        if w.sample_rate is not None and np.isfinite(w.sample_rate) and w.sample_rate > 0
    }
    if len(rates) > 1:
        raise ValueError("OpenEP export has mixed signal sampling rates; export a homogeneous map")
    notes = []
    if any(
        w.meta.get("truncated_final_row") for selected in bindings for w, _ in selected.values()
    ):
        notes.append(
            "signals: a truncated final source row was omitted; only complete samples are available"
        )
    if ambiguous:
        notes.append(f"signals: {ambiguous} ambiguous point/channel assignments omitted")
    if not rates:
        return (
            {},
            {"included": True, "points_with_bipolar": 0},
            notes + ["signals: no point-linked sampled windows available"],
        )
    rate = rates.pop()
    n = len(points)
    lengths = [len(w.data) for selected in bindings for w, _ in selected.values()]
    samples = max(lengths, default=0)
    if not samples:
        return (
            {},
            {"included": True, "points_with_bipolar": 0},
            notes + ["signals: all matched windows are empty"],
        )
    ecg_names = list(ecg_channels) if ecg_channels is not None else list(ECG_LEADS)
    # Include only leads actually present in the matched recordings.
    ecg_names = [
        name
        for name in ecg_names
        if any(
            _channel(w, name) is not None or _channel(w, "ECG " + name) is not None
            for selected in bindings
            for w, _ in selected.values()
        )
    ]
    fields = {
        "egm": np.full((n, samples), np.nan),
        "egmUni": np.full((n, samples, 2), np.nan),
        "egmRef": np.full((n, samples), np.nan),
        "egmRef2": np.full((n, samples), np.nan),
        "ecg": np.full((n, samples, len(ecg_names)), np.nan),
        "sampleFrequency": rate,
        "ecgNames": ecg_names,
        "electrodeNames_bip": [""] * n,
        "electrodeNames_uni": [["", ""] for _ in points],
        "egmUniX": np.full((n, 3, 2), np.nan),
    }
    reference = np.full(n, np.nan)
    counts = np.zeros(n, dtype=int)
    units = {
        role: [""] * n
        for role in ("bipolar", "unipolar_1", "unipolar_2", "reference", "reference_2")
    }
    ecg_units = [[""] * len(ecg_names) for _ in points]
    missing_unit = 0

    def trace(wave, column):
        nonlocal missing_unit
        unit = wave.units[column]
        if unit == "mV":
            factor, output_unit = 1.0, "mV"
        elif unit in {"V", "uV", "µV"}:
            factor, output_unit = {"V": 1000.0, "uV": 0.001, "µV": 0.001}[unit], "mV"
        elif scale_to_mv is not None:
            factor, output_unit = scale_to_mv, "mV"
        else:
            factor, output_unit = 1.0, unit
            missing_unit += 1
        return np.asarray(wave.data[:, column], float) * factor, output_unit

    for i, (point, selected) in enumerate(zip(points, bindings, strict=True)):
        primary = next(
            (
                selected[role]
                for role in ("bipolar", "unipolar_1", "unipolar_2", "reference", "reference_2")
                if role in selected
            ),
            next(iter(selected.values()), None),
        )
        if primary is None:
            continue
        window = primary[0]
        count = len(window.data)
        if window.sample_rate != rate:
            notes.append(f"signals: point {i + 1} has no valid primary sampling rate; omitted")
            continue
        counts[i] = count

        def aligned_with_primary(wave, window=window, count=count):
            # Different roles/leads share an axis only when recorded together.
            starts = (wave.meta.get("start_time"), window.meta.get("start_time"))
            same_start = wave is window or (
                None not in starts and abs(starts[0] - starts[1]) < 1e-6
            )
            return wave.sample_rate == rate and len(wave.data) == count and same_start

        for role, (wave, column) in selected.items():
            if not aligned_with_primary(wave):
                notes.append(f"signals: point {i + 1} {role} window is not aligned; omitted")
                continue
            values, unit = trace(wave, column)
            if role in units:
                units[role][i] = unit
            if role in {"bipolar", "reference", "reference_2"}:
                target = {"bipolar": "egm", "reference": "egmRef", "reference_2": "egmRef2"}[role]
                fields[target][i, :count] = values
                if role == "bipolar":
                    fields["electrodeNames_bip"][i] = wave.channels[column]
            elif role in {"unipolar_1", "unipolar_2"}:
                index = 0 if role == "unipolar_1" else 1
                fields["egmUni"][i, :count, index] = values
                label = wave.channels[column]
                fields["electrodeNames_uni"][i][index] = label
                position = (point.electrodes or {}).get(label)
                if position is not None:
                    fields["egmUniX"][i, :, index] = position
        for j, name in enumerate(ecg_names):
            hits = [
                (w, _channel(w, name))
                for w, _ in selected.values()
                if _channel(w, name) is not None
            ]
            if not hits:
                hits = [
                    (w, _channel(w, "ECG " + name))
                    for w, _ in selected.values()
                    if _channel(w, "ECG " + name) is not None
                ]
            # Several roles may point into the same CARTO window.
            unique = {(id(w), c): (w, c) for w, c in hits}
            if len(unique) == 1:
                w, c = next(iter(unique.values()))
                if aligned_with_primary(w):
                    values, unit = trace(w, c)
                    fields["ecg"][i, :count, j] = values
                    ecg_units[i][j] = unit
        annotation = point.annotations or {}
        if window.meta.get("format") == "ensite_dxl":
            # DxL explicitly numbers its waveform columns from zero. Ref Tick
            # is its recorded reference location, independent of epoch clocks.
            tick = annotation.get("reference_sample_zero_based")
            if tick is not None:
                reference[i] = float(tick) + 1
        else:
            reference[i] = annotation.get("reference", np.nan)
    if missing_unit:
        notes.append(
            "signals: some amplitudes have unknown units; values are retained without calibration, so mV-based thresholds are not justified"
        )
    matched = np.any(np.isfinite(fields["egm"]), axis=1)
    metadata = {
        "included": True,
        "points_with_bipolar": int(matched.sum()),
        "sample_counts": counts,
        "units": units,
        "ecg_units": ecg_units,
        "reference_samples": reference,
        "scale_to_mv": scale_to_mv if scale_to_mv is not None else np.nan,
    }
    notes.append(
        f"signals: {int(matched.sum())} of {n} points carry bipolar electrograms; absent samples are NaN"
    )
    return fields, metadata, notes
