"""What the MCP server can actually do.

Plain functions on a client + an anonymiser, deliberately free of any MCP
import: the wiring in :mod:`pulse_ep.mcp.server` is a few lines, while this is
where the decisions live, and it stays testable without the SDK installed.

Two rules shape every result here:

**Nothing leaves without passing the anonymiser.** Each tool ends in
``self.anon.envelope(self.anon.scrub(...))``, so protection is not something a
new tool can forget to opt into.

**Bulk data goes to a file, not into the conversation.** A mesh is tens of
thousands of vertices and a signal window is 2500 samples of 78 channels.
Everything is reachable — ``fetch_map``, ``fetch_points`` and
``fetch_waveform`` hand over the *complete* stored data — but they write it
next to the client and return the path, because a model that has the data in
a file can compute with it, while a model that has it pasted into its context
has spent the room it needed to think. The summarising tools
(``map_summary``, ``read_points``, ``read_waveform``) stay for the questions
that do not need the bulk at all.

``inline=True`` overrides that where a caller really wants the payload in the
answer; the response then says how large it is.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

import numpy as np

from pulse_ep.mcp.anonymize import Anonymiser
from pulse_ep.mcp.client import PulseEpClient

#: Waveform samples returned per channel unless asked otherwise. A 2.5 s
#: window at 1 kHz is 2500 numbers per channel; a few hundred show the shape
#: of a beat, and the statistics below are computed on the full window so
#: nothing about amplitude is lost to the decimation.
DEFAULT_MAX_SAMPLES = 400

#: Waveform rows listed at once. A study can hold thousands.
DEFAULT_WAVEFORM_LIMIT = 25

#: Measurement points returned inline per page. A map holds a few hundred to a
#: few thousand; ``fetch_points`` writes all of them at once instead.
DEFAULT_POINT_LIMIT = 200

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class Tools:
    """The read-only operations the MCP server exposes."""

    def __init__(
        self, client: PulseEpClient, anon: Anonymiser, download_dir: str | Path | None = None
    ) -> None:
        self.client = client
        self.anon = anon
        #: Where bulk downloads land. One directory, and every file goes into
        #: it by basename: a filename that arrives as an argument must never
        #: be able to write outside it or over something it did not create.
        self.download_dir = Path(download_dir or Path(tempfile.gettempdir()) / "pulse-ep-mcp")

    def _target(self, filename: str | None, default: str) -> Path:
        name = _SAFE_NAME.sub("_", Path(filename or default).name).strip("._") or default
        self.download_dir.mkdir(parents=True, exist_ok=True)
        return self.download_dir / name

    # -- studies and maps -------------------------------------------------

    def list_studies(self) -> dict:
        """Every study in the database."""
        studies = [
            {
                "study_id": s.get("id"),
                "study": self.anon.alias(s.get("id"), s.get("study_name")),
                "vendor": s.get("vendor"),
            }
            for s in self.client.studies()
        ]
        return self.anon.envelope({"count": len(studies), "studies": studies})

    def list_maps(self, study_id: int) -> dict:
        """The EP maps of one study, with how many points each really holds."""
        maps = self.client.maps(study_id)
        return self.anon.envelope(
            self.anon.scrub(
                {
                    "study_id": int(study_id),
                    "study": self.anon.alias(int(study_id)),
                    "count": len(maps),
                    "maps": [
                        {
                            "map_id": m.get("id"),
                            "map_name": m.get("map_name"),
                            "points_reported_by_vendor": m.get("number_of_points"),
                            "measurement_points": m.get("measurement_points"),
                        }
                        for m in maps
                    ],
                }
            )
        )

    def map_summary(self, map_id: int) -> dict:
        """What a map measured: its quantities, their units and their ranges.

        The first question about any map, and the one a raw mesh download is
        the worst possible way to answer.
        """
        scalars = self.client.scalars(map_id)
        try:
            attributes = (self.client.attributes(map_id) or {}).get("attributes") or {}
        except Exception:  # attributes are optional metadata, not the answer
            attributes = {}
        return self.anon.envelope(
            self.anon.scrub(
                {
                    "map_id": int(map_id),
                    "primary_scalar": scalars.get("primary"),
                    "scalars": [
                        {
                            "name": s.get("name"),
                            "kind": s.get("kind"),
                            "unit": s.get("unit"),
                            "min": s.get("min"),
                            "max": s.get("max"),
                            "n_valid": s.get("n_valid"),
                        }
                        for s in scalars.get("scalars", [])
                    ],
                    "attributes": attributes,
                }
            )
        )

    # -- the whole thing --------------------------------------------------

    def read_points(self, map_id: int, limit: int = DEFAULT_POINT_LIMIT, offset: int = 0) -> dict:
        """The map's acquisition points and their measurements, paged.

        Points are small enough to read directly — a few hundred to a few
        thousand per map — so this returns them in the answer. Ask for the
        whole set at once with ``fetch_points`` when you mean to compute with
        it rather than look at it.
        """
        body = self.client.points(map_id, limit=limit, offset=offset)
        return self.anon.envelope(
            self.anon.scrub(
                {
                    "map_id": int(map_id),
                    "count": body.get("count"),
                    "offset": body.get("offset"),
                    "returned": body.get("returned"),
                    "units": body.get("units"),
                    "points": body.get("points", []),
                }
            )
        )

    def fetch_map(
        self,
        map_id: int,
        scalar_name: str | None = None,
        filename: str | None = None,
        inline: bool = False,
    ) -> dict:
        """Download the **complete** stored map — mesh, every scalar field,
        every point, the signal index — as JSON.

        Written to a file and the path returned, because a 13 000-vertex mesh
        is megabytes: in a file it can be computed with, in a context window
        it only fills it. Pass ``inline=True`` to get the payload in the
        answer instead, and mind the size the response reports.

        The file is the ``representation=raw`` export — stored,
        importer-conditioned data with no rendering applied.
        """
        payload = self.anon.scrub(self.client.mesh_raw(map_id, scalar_name))
        mesh = payload.get("mesh_data") or {}
        summary = {
            "map_id": int(map_id),
            "scalar_name": payload.get("scalar_name"),
            "n_vertices": len(mesh.get("vertices") or []),
            "n_triangles": len(mesh.get("faces") or []),
            "scalar_fields": list((mesh.get("scalar_fields") or {}).keys()),
            "n_points": len((payload.get("point_data") or {}).get("measurement_points") or []),
            "n_waveforms": len(payload.get("waveforms") or []),
        }
        text = json.dumps(payload)
        if inline:
            return self.anon.envelope({**summary, "bytes": len(text), "data": payload})

        path = self._target(filename, f"map-{int(map_id)}.json")
        path.write_text(text, encoding="utf-8")
        return self.anon.envelope(
            {**summary, "path": str(path), "bytes": path.stat().st_size, "format": "json"}
        )

    def fetch_points(self, map_id: int, filename: str | None = None) -> dict:
        """Write **every** measurement point of a map as CSV.

        One row per point, one column per quantity — the shape that loads into
        pandas, R or a spreadsheet without further work. Maps differ in which
        quantities they carry, so the columns are those this map actually has.
        """
        body = self.client.points(map_id, limit=0)
        points = body.get("points", [])
        quantities = sorted({name for p in points for name in (p.get("measurements") or {})})
        # A flat table needs self-describing headers, so the annotation group
        # is prefixed; the keys are the ones the API and a stored waveform use.
        annotations = sorted({key for p in points for key in (p.get("annotations") or {})})

        path = self._target(filename, f"map-{int(map_id)}-points.csv")
        columns = [
            "point_index",
            "source_id",
            "x",
            "y",
            "z",
            *quantities,
            *[f"annotation_{key}" for key in annotations],
            "tags",
        ]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            for point in points:
                position = point.get("position") or [None, None, None]
                measurements = point.get("measurements") or {}
                point_annotations = point.get("annotations") or {}
                writer.writerow(
                    [
                        point.get("point_index"),
                        point.get("source_id"),
                        *position[:3],
                        *[measurements.get(q) for q in quantities],
                        *[point_annotations.get(key) for key in annotations],
                        ";".join(point.get("tags") or []),
                    ]
                )
        return self.anon.envelope(
            {
                "map_id": int(map_id),
                "path": str(path),
                "bytes": path.stat().st_size,
                "format": "csv",
                "count": len(points),
                "columns": columns,
                "units": body.get("units"),
            }
        )

    def fetch_waveform(self, waveform_id: int, filename: str | None = None) -> dict:
        """Write one signal window's **full** samples as Parquet.

        The stored file verbatim: every channel, every sample, readable by
        pandas / Arrow / R / MATLAB. ``read_waveform`` is the version that
        answers a question instead of handing over the recording.
        """
        data = self.client.waveform_bytes(waveform_id)
        path = self._target(filename, f"waveform-{int(waveform_id)}.parquet")
        path.write_bytes(data)

        from pulse_ep.core.waveform import waveform_from_parquet

        wave = waveform_from_parquet(path)
        # Scrub what came from the server, then add the local file — the
        # download path is the answer to this tool, and the anonymiser (rightly)
        # redacts anything path-shaped that passes through it.
        details = self.anon.scrub(
            {
                "waveform_id": int(waveform_id),
                "n_samples": int(wave.data.shape[0]),
                "n_channels": int(wave.data.shape[1]),
                "sample_rate": wave.sample_rate,
                "channels": list(wave.channels),
                "unit": "mV",
            }
        )
        return self.anon.envelope(
            {**details, "path": str(path), "bytes": len(data), "format": "parquet"}
        )

    # -- analysis ---------------------------------------------------------

    def area_of_range(
        self,
        map_id: int,
        min_value: float,
        max_value: float,
        scalar_name: str | None = None,
        distance: float = 5.0,
    ) -> dict:
        """Surface area of the map between two values of a quantity.

        The low-voltage or scar-area question. ``distance`` is the confidence
        mask in mm: vertices farther than that from a real measurement are not
        counted.

        The area is in cm² — stated in the result rather than left for the
        reader to infer, as every other quantity here is.
        """
        result = self.client.areas(
            map_id,
            [[float(min_value), float(max_value)]],
            scalar_name=scalar_name,
            distance=distance,
        )
        areas = result.get("areas") or [None]
        return self.anon.envelope(
            {
                "map_id": int(map_id),
                "scalar_name": scalar_name,
                "range": [float(min_value), float(max_value)],
                "distance_threshold_mm": distance,
                "area": areas[0],
                "unit": "cm2",
                "area_unit": "cm^2",
            }
        )

    def compare_maps(
        self,
        map_a_id: int,
        map_b_id: int,
        scalar_name: str,
        metric: str = "euclidean",
        max_distance: float | None = None,
    ) -> dict:
        """Difference between two maps of the same chamber, as statistics.

        ``metric`` decides what "the same place" means: ``euclidean`` takes the
        nearest vertex in space, ``geodesic`` the nearest one along the
        surface, which avoids pairing across a thin wall.
        """
        options = {"metric": metric}
        if max_distance is not None:
            options["max_distance"] = float(max_distance)
        result = self.client.compare(map_a_id, map_b_id, scalar_name, **options)
        return self.anon.envelope(
            {
                "map_a_id": int(map_a_id),
                "map_b_id": int(map_b_id),
                "scalar_name": result.get("scalar_name", scalar_name),
                "metric": result.get("metric", metric),
                "n_masked": result.get("n_masked"),
                "stats": result.get("stats"),
            }
        )

    # -- signals ----------------------------------------------------------

    def list_waveforms(
        self, map_id: int, limit: int = DEFAULT_WAVEFORM_LIMIT, offset: int = 0
    ) -> dict:
        """The signal windows recorded for a map (metadata only).

        A CARTO study holds one window per acquisition and one row per point
        taken from it, so this is paged: the summary describes all of them,
        the rows are a window onto them.
        """
        body = self.client.waveforms(map_id)
        rows = body.get("waveforms", [])
        page = rows[int(offset) : int(offset) + int(limit)]
        channels = sorted({c for r in rows for c in (r.get("channels") or [])})
        return self.anon.envelope(
            self.anon.scrub(
                {
                    "map_id": int(map_id),
                    "count": len(rows),
                    "offset": int(offset),
                    "returned": len(page),
                    "sample_rates": sorted(
                        {r.get("sample_rate") for r in rows if r.get("sample_rate")}
                    ),
                    "channels_available": channels,
                    "waveforms": [
                        {
                            "waveform_id": r.get("id"),
                            "point": r.get("point_source_id"),
                            "signal_type": r.get("signal_type"),
                            "n_samples": r.get("n_samples"),
                            "n_channels": r.get("n_channels"),
                        }
                        for r in page
                    ],
                }
            )
        )

    def read_waveform(
        self,
        waveform_id: int,
        channels: list[str] | None = None,
        start_ms: float | None = None,
        end_ms: float | None = None,
        max_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> dict:
        """Read one signal window: statistics, and the trace of named channels.

        Without ``channels`` the traces of the channels the point was
        *annotated* on are returned (mapping uni- and bipole, reference) —
        naming all 78 would be neither useful nor readable. The channel list
        comes back either way, so a follow-up call can ask for another one.

        ``start_ms`` / ``end_ms`` are offsets from the start of the window.
        """
        from pulse_ep.core.waveform import waveform_from_parquet

        wave = waveform_from_parquet(self.client.waveform_bytes(waveform_id))
        meta = wave.meta or {}
        points = meta.get("points") or []

        requested = list(channels) if channels else _annotated_channels(points)
        known = [c for c in requested if c in wave.channels]
        unknown = [c for c in requested if c not in wave.channels]

        data, time = _slice(wave, start_ms, end_ms)
        step = max(1, int(np.ceil(len(data) / max(1, int(max_samples))))) if len(data) else 1

        series, stats = {}, {}
        for channel in known:
            column = data[:, wave.channels.index(channel)]
            finite = column[np.isfinite(column)]
            # statistics over every sample of the window, not over the
            # decimated trace: peak amplitude is exactly what decimation drops
            stats[channel] = {
                "min": float(finite.min()) if finite.size else None,
                "max": float(finite.max()) if finite.size else None,
                "mean": float(finite.mean()) if finite.size else None,
            }
            series[channel] = [round(float(v), 4) for v in column[::step]]

        return self.anon.envelope(
            self.anon.scrub(
                {
                    "waveform_id": int(waveform_id),
                    "sample_rate": wave.sample_rate,
                    "unit": "mV",
                    "n_samples_in_window": int(len(data)),
                    "decimation": step,
                    "samples_returned": len(next(iter(series.values()), [])),
                    "t_start": None if time is None or not len(time) else float(time[0]),
                    "channels_returned": known,
                    "channels_unknown": unknown,
                    "channels_available": list(wave.channels),
                    "points": [
                        {
                            "point": p.get("point_id"),
                            "mapping_channels": p.get("mapping_channels"),
                            "annotations": p.get("annotations"),
                        }
                        for p in points
                    ],
                    "stats": stats,
                    "series": series,
                }
            )
        )


def _annotated_channels(points: list[dict]) -> list[str]:
    """The channels the acquisition itself considered relevant."""
    channels = []
    for point in points:
        for name in (point.get("mapping_channels") or {}).values():
            if name and name not in channels:
                channels.append(name)
    return channels


def _slice(wave, start_ms, end_ms):
    """The requested part of a window, by millisecond offset from its start.

    Milliseconds are converted through the sample rate rather than used as
    indices: CARTO records at 1 kHz, where the two happen to coincide, and an
    EnSite X segment at 2 kHz, where treating one as the other would silently
    return half the window the caller asked for.
    """
    data, time = wave.data, wave.time
    if start_ms is None and end_ms is None:
        return data, time
    per_ms = (wave.sample_rate or 1000.0) / 1000.0
    n = len(data)
    first = 0 if start_ms is None else max(0, int(round(float(start_ms) * per_ms)))
    last = n if end_ms is None else min(n, int(round(float(end_ms) * per_ms)))
    if last <= first:
        return data[:0], None if time is None else time[:0]
    return data[first:last], None if time is None else time[first:last]
