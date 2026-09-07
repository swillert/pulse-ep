"""Execute a reproducible MCP tool sequence against a running pulse-ep service.

Uses the standard PULSE_EP_MCP_* connection environment. Downloads remain in
PULSE_EP_MCP_DOWNLOAD_DIR. The output contains aggregate results only.
"""

import argparse
import asyncio
import csv
import json
import math
import os
import statistics
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def analyse(map_id: int):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "pulse_ep.mcp.server"], env=dict(os.environ)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError(f"MCP tool failed: {name}")
                if result.structuredContent is not None:
                    return result.structuredContent
                return json.loads(next(c.text for c in result.content if c.type == "text"))

            summary = await call("map_summary", {"map_id": map_id})
            field = next(s for s in summary["scalars"] if s["name"] == "voltage_bipolar")
            if field["unit"] != "mV":
                raise ValueError("This example requires bipolar voltage in mV")
            area = await call(
                "area_of_range",
                {
                    "map_id": map_id,
                    "min_value": 0,
                    "max_value": 0.5,
                    "scalar_name": "voltage_bipolar",
                    "distance": 5,
                },
            )
            download = await call("fetch_points", {"map_id": map_id})
            with Path(download["path"]).open(newline="") as fh:
                rows = list(csv.DictReader(fh))
            values = [float(r["voltage_bipolar"]) for r in rows if r["voltage_bipolar"]]
            values = [v for v in values if math.isfinite(v)]
            if len(rows) != download["count"] or not values:
                raise ValueError(
                    "Downloaded point table is incomplete or contains no finite values"
                )
            return {
                "transport": "MCP stdio",
                "scalar": field,
                "interval_mv": [0, 0.5],
                "distance_threshold_mm": 5,
                "area_cm2": area["area"],
                "downloaded_points": len(rows),
                "finite_point_values": len(values),
                "point_voltage_median_mv": statistics.median(values),
                "anonymized": all(x["anonymized"] for x in (summary, area, download)),
            }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-id", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(analyse(args.map_id)), indent=2))
