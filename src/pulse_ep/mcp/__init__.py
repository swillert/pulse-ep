"""MCP server for pulse-ep — read-only access for an AI client.

A fourth peer beside the REST API, the viewer and the Python toolkit, and a
client of the same JWT endpoints as the others. It exists for the questions
plain SQL on the database cannot answer: signal samples (stored outside the
database as Parquet), the meaning and range of a map's scalar fields, and the
operations that are computation rather than query.

Study identity is anonymised by default — see :mod:`pulse_ep.mcp.anonymize`.
"""

from pulse_ep.mcp.anonymize import Anonymiser, anonymiser_from_env
from pulse_ep.mcp.client import PulseEpClient, PulseEpError, client_from_env
from pulse_ep.mcp.tools import Tools

__all__ = [
    "Anonymiser",
    "PulseEpClient",
    "PulseEpError",
    "Tools",
    "anonymiser_from_env",
    "client_from_env",
]
