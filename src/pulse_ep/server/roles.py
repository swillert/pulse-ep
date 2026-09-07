"""Who may do what.

Every authenticated endpoint used to accept every account. The ``role`` claim
was minted at login and never read again — so the four endpoints the REST
reference calls "admin only" were not, and the read-only account the MCP guide
recommends could set attributes, delete colormaps and delete reports.

The roles themselves are :mod:`pulse_ep.core.roles`; this is where they are
enforced. The rule is about *writing*, not about vendor or study, and several
reads arrive as POSTs (a filter, an area integration, a comparison) — those
stay open, because the decision is what an endpoint *does*, not which verb it
came under.
"""

from __future__ import annotations

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from pulse_ep.core.roles import ADMIN, DEFAULT_ROLE, READONLY, ROLES, USER, WRITERS

__all__ = ["ADMIN", "READONLY", "ROLES", "USER", "WRITERS", "admin_only", "require_role", "writes"]


def require_role(*allowed: str):
    """Refuse an authenticated caller whose role is not in ``allowed``.

    Wraps ``jwt_required`` rather than sitting beside it, so an endpoint can
    never be role-guarded but unauthenticated, or ordered the wrong way round.

    An account whose role predates this — or one the deployment renamed — is
    treated as :data:`USER`: the historical behaviour of every account, which
    keeps an upgrade from locking existing users out of what they could
    already do. It is not treated as ``admin``.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            role = (get_jwt() or {}).get("role") or DEFAULT_ROLE
            if role not in ROLES:
                role = DEFAULT_ROLE
            if role not in allowed:
                return (
                    jsonify(
                        {
                            "error": "insufficient role",
                            "role": role,
                            "required": sorted(allowed),
                        }
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapper

    return decorator


def writes(view):
    """Mark an endpoint as changing stored state: everyone but ``readonly``."""
    return require_role(*WRITERS)(view)


def admin_only(view):
    """Mark an endpoint as reserved for administrators."""
    return require_role(ADMIN)(view)
