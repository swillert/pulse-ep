"""Vendor-specific importers that decode raw exports into vendor-neutral
domain objects (:class:`pulse_ep.EPMap` / :class:`pulse_ep.Study`).

Each vendor's decode quirks live here; the core domain layer stays
semantics-agnostic.
"""

# Import vendor modules so they register themselves with the importer
# registry (see ``base.detect_vendor``).
from pulse_ep.core.importers import carto as carto  # noqa: F401
from pulse_ep.core.importers import ensite as ensite  # noqa: F401
