"""Waveform storage — signals live OUT of the relational DB.

A :class:`Waveform` is a (samples × channels) time series. Stored as
**Parquet** (columnar, compressed, and readable natively by R / MATLAB /
Julia / pandas via Arrow/DuckDB) behind a :class:`WaveformStore` abstraction
so "filesystem now, object store later" is a config change. The relational
DB keeps only metadata + the returned ``uri``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

_TIME_COL = "__time__"
_META_KEY = b"pulse_ep_waveform"

#: The unit of a channel nobody has declared one for. Explicit, because the
#: alternative is a number whose meaning has to be guessed at every read site —
#: which is the design :class:`~pulse_ep.core.scalar_field.ScalarField`
#: replaced for per-vertex values.
UNKNOWN_UNIT = "unknown"


@dataclass
class Waveform:
    """A per-channel time series (``data`` is samples × channels).

    ``units`` runs parallel to ``channels``, one entry each. It is per channel
    and not per waveform because a single vendor file mixes them: EnSite X's
    ``Contact_Force_Computed`` carries force in grams, angles in degrees and
    cavity distances in millimetres side by side, and its magnetic location
    export puts a dimensionless quaternion next to a translation in mm. One
    unit for the file would be wrong for most of its columns.

    Electrograms were all millivolts, so the unit could stay a convention.
    It cannot once positions and forces live here too.
    """

    data: np.ndarray
    channels: list[str]
    sample_rate: float | None = None
    signal_type: str = ""  # egm_bipolar | egm_unipolar | ecg | force | position
    time: np.ndarray | None = None  # optional per-sample timestamps
    meta: dict = field(default_factory=dict)  # filters, segment, study, …
    units: list[str] = field(default_factory=list)  # parallel to ``channels``

    def __post_init__(self) -> None:
        # Always as long as ``channels``: a short or absent list would put the
        # burden of that check on every reader.
        given = list(self.units or [])
        self.units = [
            given[i] if i < len(given) and given[i] else UNKNOWN_UNIT
            for i in range(len(self.channels))
        ]

    def unit(self, channel: str) -> str:
        """The unit of ``channel``, or ``unknown`` if it is not one of ours."""
        try:
            return self.units[self.channels.index(channel)]
        except ValueError:
            return UNKNOWN_UNIT


@runtime_checkable
class WaveformStore(Protocol):
    def write(self, waveform: Waveform, key: str) -> str:
        """Persist ``waveform`` under ``key``; return a store-relative uri."""
        ...

    def read(
        self,
        uri: str,
        channels: list[str] | None = None,
        time_range: tuple[float, float] | None = None,
    ) -> Waveform:
        """Load a waveform, optionally projecting channels / slicing time."""
        ...

    def size(self, uri: str) -> int | None:
        """Bytes the stored window occupies, or ``None`` if the store cannot say.

        What a client is about to download. Only the store knows it — the
        window itself is an array in memory, and Parquet's compression means
        the number cannot be derived from the sample count.
        """
        ...


def _to_table(w: Waveform) -> pa.Table:
    arrays: dict[str, np.ndarray] = {}
    if w.time is not None:
        arrays[_TIME_COL] = np.asarray(w.time)
    for i, channel in enumerate(w.channels):
        arrays[channel] = np.asarray(w.data[:, i])
    table = pa.table(arrays)
    meta = {
        "sample_rate": w.sample_rate,
        "signal_type": w.signal_type,
        "channels": w.channels,
        "units": w.units,
        "meta": w.meta,
    }
    return table.replace_schema_metadata(
        {**(table.schema.metadata or {}), _META_KEY: json.dumps(meta).encode()}
    )


def _from_table(
    table: pa.Table,
    channels: list[str] | None,
    time_range: tuple[float, float] | None,
) -> Waveform:
    md_bytes = (table.schema.metadata or {}).get(_META_KEY)
    md = json.loads(md_bytes) if md_bytes else {}
    names = table.column_names
    stored_channels = md.get("channels") or [c for c in names if c != _TIME_COL]
    selected = channels if channels is not None else stored_channels
    # Units follow the *projection*, not the stored order: asking for two of
    # eight channels must not hand back the first two channels' units. A file
    # written before units existed reads back as unknown, not as absent.
    stored_units = md.get("units") or []
    by_channel = {
        ch: (stored_units[i] if i < len(stored_units) else UNKNOWN_UNIT)
        for i, ch in enumerate(stored_channels)
    }
    units = [by_channel.get(ch, UNKNOWN_UNIT) for ch in selected]

    time = table.column(_TIME_COL).to_numpy() if _TIME_COL in names else None
    if selected:
        data = np.column_stack([table.column(ch).to_numpy() for ch in selected])
    else:
        data = np.empty((table.num_rows, 0))

    if time_range is not None and time is not None:
        lo, hi = time_range
        mask = (time >= lo) & (time <= hi)
        data, time = data[mask], time[mask]

    return Waveform(
        data=data,
        channels=list(selected),
        sample_rate=md.get("sample_rate"),
        signal_type=md.get("signal_type", ""),
        time=time,
        meta=md.get("meta", {}),
        units=units,
    )


def waveform_from_parquet(
    source: bytes | str | Path,
    channels: list[str] | None = None,
    time_range: tuple[float, float] | None = None,
) -> Waveform:
    """Read a stored waveform back from Parquet bytes or a file path.

    A downloaded waveform is a Parquet file with no store around it — that is
    what ``/waveforms/<id>/download`` hands a client, and every consumer of it
    otherwise has to know how the channels and metadata are laid out inside.
    """
    if isinstance(source, (str, Path)):
        table = pq.read_table(source)
    else:
        table = pq.read_table(pa.BufferReader(source))
    return _from_table(table, channels, time_range)


class FilesystemStore:
    """Store waveforms as Parquet files under a root directory.

    ``key`` is typically ``f"{study_id}/{waveform_id}"`` so a study's signals
    live under one folder (easy retention: delete the folder).
    """

    ext = ".parquet"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(self, waveform: Waveform, key: str) -> str:
        rel = f"{key}{self.ext}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(_to_table(waveform), path, compression="zstd")
        return rel

    def size(self, uri: str) -> int | None:
        try:
            return (self.root / uri).stat().st_size
        except OSError:
            return None

    def read(
        self,
        uri: str,
        channels: list[str] | None = None,
        time_range: tuple[float, float] | None = None,
    ) -> Waveform:
        path = self.root / uri
        columns = None
        if channels is not None:  # columnar projection — only read needed channels
            names = pq.read_schema(path).names
            columns = ([_TIME_COL] if _TIME_COL in names else []) + list(channels)
        return _from_table(pq.read_table(path, columns=columns), channels, time_range)
