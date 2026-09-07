"""Who may do what — the vocabulary.

Closed and curated, like the scalar-field inventory: a role is added here
once, deliberately. *Enforcing* it is the server's business
(:mod:`pulse_ep.server.roles`), so the CLI can name a role without pulling
Flask in — ``pulse-ep-create-user`` is usable from a core install and stays
that way.

``admin``
    Everything, including creating users and editing the shared colormaps and
    map attributes every other account sees.
``user``
    The ordinary account: read everything, run analyses, save and generate
    reports, drive an import.
``readonly``
    Reads only, refused on every endpoint that changes stored state. This is
    the account to give an MCP server: it is what makes "read-only access"
    a property of the deployment rather than a promise in a document.
"""

from __future__ import annotations

ADMIN = "admin"
USER = "user"
READONLY = "readonly"

#: Every role this deployment knows, most privileged first.
ROLES = (ADMIN, USER, READONLY)

#: Roles allowed to change stored state. ``readonly`` is not one of them.
WRITERS = (ADMIN, USER)

#: What an account with no usable role claim is treated as — the historical
#: behaviour of every account, so an upgrade locks nobody out of what they
#: could already do, and promotes nobody either.
DEFAULT_ROLE = USER
