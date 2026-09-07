"""``pulse-ep-mcp`` — the MCP server, a fourth peer beside viewer and toolkit.

It exposes what SQL on the database cannot answer: signal samples (which live
outside the database as Parquet), the meaning and range of a map's scalar
fields (a JSONB blob of tens of thousands of numbers, per field), and the
operations — area, comparison — that are computation rather than query.

Everything it can do is **read-only**. Importing, tagging and deleting stay
with the CLI and the review UI, where a person is present.

Configuration (environment, or the flags below):

===============================  ==============================================
``PULSE_EP_MCP_BASE_URL``        pulse-ep server (default http://localhost:5000)
``PULSE_EP_MCP_TOKEN``           a JWT, or …
``PULSE_EP_MCP_USERNAME/PASSWORD`` … an account to log in with
``PULSE_EP_MCP_ENABLED``         ``1`` explicitly enables serving (default: off)
``PULSE_EP_MCP_ANONYMIZE``       ``0`` turns anonymisation off (default: on)
``PULSE_EP_MCP_DOWNLOAD_DIR``    where bulk downloads are written
===============================  ==============================================
"""

from __future__ import annotations

import argparse
import os
import sys

from pulse_ep.core.config import TRUE_VALUES
from pulse_ep.mcp.anonymize import anonymiser_from_env
from pulse_ep.mcp.client import MCPDisabled, PulseEpError, client_from_env
from pulse_ep.mcp.tools import (
    DEFAULT_MAX_SAMPLES,
    DEFAULT_POINT_LIMIT,
    DEFAULT_WAVEFORM_LIMIT,
    Tools,
)

INSTRUCTIONS = """\
Read-only access to a pulse-ep electroanatomical mapping database.

Start at list_studies, then list_maps, then map_summary — a map's quantities
are vendor-neutral names (activation_time, voltage_bipolar, pacemap_score, …)
that mean the same thing for CARTO and EnSite X studies.

Everything stored is reachable. Summarising tools (map_summary, read_points,
read_waveform) answer questions directly; fetch_map, fetch_points and
fetch_waveform hand over the complete data as a file next to you, which is
what you want whenever you mean to compute with it rather than read it.
"""


def build_server(tools: Tools, anonymized: bool):
    """Wire the tools into a FastMCP server.

    Note what is *not* here: no tool switches anonymisation. That is the
    operator's decision, taken when the server is started; a model must not be
    able to lift the restriction it is under.
    """
    from mcp.server.fastmcp import FastMCP

    mode = "anonymised" if anonymized else "NOT anonymised — study names are real"
    mcp = FastMCP("pulse-ep", instructions=f"{INSTRUCTIONS}\nStudy identity: {mode}.")

    @mcp.tool()
    def list_studies() -> dict:
        """List the studies in the database (id, name, vendor)."""
        return tools.list_studies()

    @mcp.tool()
    def list_maps(study_id: int) -> dict:
        """List a study's EP maps and how many measurement points each holds."""
        return tools.list_maps(study_id)

    @mcp.tool()
    def map_summary(map_id: int) -> dict:
        """What a map measured: its quantities, their units, ranges and attributes."""
        return tools.map_summary(map_id)

    @mcp.tool()
    def read_points(map_id: int, limit: int = DEFAULT_POINT_LIMIT, offset: int = 0) -> dict:
        """The map's acquisition points and their measurements, paged."""
        return tools.read_points(map_id, limit, offset)

    @mcp.tool()
    def fetch_map(
        map_id: int,
        scalar_name: str | None = None,
        filename: str | None = None,
        inline: bool = False,
    ) -> dict:
        """Download the complete stored map — mesh, all scalar fields, points.

        Writes JSON next to you and returns the path, so you can compute with
        it; `inline=True` puts the whole payload in the answer instead.
        """
        return tools.fetch_map(map_id, scalar_name, filename, inline)

    @mcp.tool()
    def fetch_points(map_id: int, filename: str | None = None) -> dict:
        """Write every measurement point of a map as CSV; returns the path."""
        return tools.fetch_points(map_id, filename)

    @mcp.tool()
    def fetch_waveform(waveform_id: int, filename: str | None = None) -> dict:
        """Write one signal window's full samples as Parquet; returns the path."""
        return tools.fetch_waveform(waveform_id, filename)

    @mcp.tool()
    def area_of_range(
        map_id: int,
        min_value: float,
        max_value: float,
        scalar_name: str | None = None,
        distance: float = 5.0,
    ) -> dict:
        """Surface area of a map between two values of a quantity.

        The low-voltage / scar-area question. `distance` (mm) is the
        confidence mask: vertices farther than that from a real measurement
        are not counted.
        """
        return tools.area_of_range(map_id, min_value, max_value, scalar_name, distance)

    @mcp.tool()
    def compare_maps(
        map_a_id: int,
        map_b_id: int,
        scalar_name: str,
        metric: str = "euclidean",
        max_distance: float | None = None,
    ) -> dict:
        """Compare two maps of the same chamber; returns difference statistics.

        `metric`: "euclidean" pairs the nearest vertex in space, "geodesic"
        the nearest one along the surface (which does not pair across a wall).
        """
        return tools.compare_maps(map_a_id, map_b_id, scalar_name, metric, max_distance)

    @mcp.tool()
    def list_waveforms(map_id: int, limit: int = DEFAULT_WAVEFORM_LIMIT, offset: int = 0) -> dict:
        """List the signal windows recorded for a map (metadata only, paged)."""
        return tools.list_waveforms(map_id, limit, offset)

    @mcp.tool()
    def read_waveform(
        waveform_id: int,
        channels: list[str] | None = None,
        start_ms: float | None = None,
        end_ms: float | None = None,
        max_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> dict:
        """Read one signal window: per-channel statistics and a decimated trace.

        Without `channels`, returns the channels the point was annotated on
        (mapping bipole/unipole and reference). Statistics are computed over
        every sample; the returned trace is decimated to `max_samples`.
        """
        return tools.read_waveform(waveform_id, channels, start_ms, end_ms, max_samples)

    return mcp


#: The strings that switch the server on — the set the server-side
#: ``Settings.mcp_enabled`` uses, imported rather than repeated so the two
#: cannot drift. Everything else leaves it off: this fails *closed*, like the
#: anonymiser and for a stronger reason: the switch is what lets study data
#: reach a language model, so the direction a mistake falls in must be the one
#: that sends nothing.
_ON = TRUE_VALUES


def is_enabled(env, override: bool | None = None) -> bool:
    """Whether this MCP server may serve at all.

    Off unless the environment explicitly says otherwise: AI access is opted
    into, never inherited from a default.

    Two switches, one name. This is the local one — it stops the process here,
    which is what a workstation wants. The one that decides for a *deployment*
    lives on the server (``PULSE_EP_MCP_ENABLED`` there): it refuses requests
    that identify themselves as MCP, so the answer does not depend on whoever
    starts this process. Neither is a boundary against a person holding valid
    credentials; the account is (see the MCP guide).
    """
    if override is not None:
        return override
    return str(env.get("PULSE_EP_MCP_ENABLED", "")).strip().casefold() in _ON


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-mcp",
        description="MCP server exposing a pulse-ep deployment read-only to an AI client.",
    )
    p.add_argument("--base-url", help="pulse-ep server (default: PULSE_EP_MCP_BASE_URL).")
    p.add_argument(
        "--download-dir",
        help="Where fetch_* tools write bulk data (default: PULSE_EP_MCP_DOWNLOAD_DIR).",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--anonymize",
        dest="anonymize",
        action="store_true",
        default=None,
        help="Replace study names with study/<id> (the default).",
    )
    group.add_argument(
        "--no-anonymize",
        dest="anonymize",
        action="store_false",
        help="Send real study names. They carry case numbers and initials.",
    )
    switch = p.add_mutually_exclusive_group()
    switch.add_argument(
        "--enabled",
        dest="enabled",
        action="store_true",
        default=None,
        help="Serve for this run. Off unless PULSE_EP_MCP_ENABLED=1.",
    )
    switch.add_argument(
        "--disabled",
        dest="enabled",
        action="store_false",
        help="Do not serve (the default). Refuses to start, and says so.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Verify configuration and connectivity, print what would be exposed, exit.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    env = dict(os.environ)
    if args.base_url:
        env["PULSE_EP_MCP_BASE_URL"] = args.base_url
    if args.download_dir:
        env["PULSE_EP_MCP_DOWNLOAD_DIR"] = args.download_dir

    if not is_enabled(env, override=args.enabled):
        # Exit code 0: switched off on purpose is not a failure, and a client
        # that restarts a "crashed" server would fight the setting.
        print(
            "pulse-ep-mcp: not enabled. No tools are served. AI access is "
            "opt-in: set PULSE_EP_MCP_ENABLED=1, here and on the server, once "
            "you have established what your data may be sent to a language "
            "model (see the MCP guide).",
            file=sys.stderr,
        )
        return 0

    client = client_from_env(env)
    anon = anonymiser_from_env(env, override=args.anonymize)
    tools = Tools(client, anon, download_dir=env.get("PULSE_EP_MCP_DOWNLOAD_DIR") or None)

    if not anon.enabled:
        # On stderr, so it is visible in the client's server log without
        # becoming part of any answer: an unanonymised session should never be
        # one nobody noticed starting.
        print(
            "pulse-ep-mcp: anonymisation is OFF — real study names "
            "(case numbers, initials) will be sent to the model.",
            file=sys.stderr,
        )

    if args.check:
        try:
            studies = tools.list_studies()
        except MCPDisabled as exc:
            # The deployment's decision, not a misconfiguration here.
            print(f"pulse-ep-mcp: {exc}", file=sys.stderr)
            return 3
        except PulseEpError as exc:
            print(f"pulse-ep-mcp: {exc}", file=sys.stderr)
            return 2
        print(f"connected to {client.base_url}")
        print(f"anonymised: {studies['anonymized']}")
        print(f"studies visible: {studies['count']}")
        print(f"downloads go to: {tools.download_dir}")
        for study in studies["studies"][:5]:
            print(f"  {study['study']}  ({study['vendor']})")
        return 0

    build_server(tools, anon.enabled).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
