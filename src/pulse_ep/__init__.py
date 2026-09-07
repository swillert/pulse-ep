"""pulse-ep — open-source platform for multivendor electroanatomical mapping data.

Quick-access re-exports of the most commonly used items::

    from pulse_ep import (
        EPMap,            # domain class: mesh + scalar fields + areas
        Study,            # container of EPMaps
        EPMapModel,       # ORM model for an EP map
        StudyModel,       # ORM model for a study
        Base,             # SQLAlchemy declarative base
        get_db_session,   # transactional context manager
        import_carto,     # ingest a single CARTO export
        import_studies,   # batch ingest from a study CSV
        read_carto_mesh,  # parse a CARTO mesh text file
    )

For deeper access, use :mod:`pulse_ep.core` directly.
"""

from __future__ import annotations

__version__ = "0.6.0"

from pulse_ep.core.database import get_db_session
from pulse_ep.core.epmap import EPMap
from pulse_ep.core.importer import (
    discover_carto_exports,
    get_filenames_from_csv,
    import_carto,
    import_studies,
)
from pulse_ep.core.mesh_proc import read_carto_mesh_file as read_carto_mesh
from pulse_ep.core.models import (
    AttributeMetadata,
    Base,
    ColormapModel,
    EPMapAttributes,
    EPMapModel,
    EPMapPoint,
    ReportModel,
    StudyModel,
    UserModel,
)
from pulse_ep.core.study import Study

__all__ = [
    "__version__",
    # Domain
    "EPMap",
    "Study",
    # ORM models
    "Base",
    "StudyModel",
    "EPMapModel",
    "EPMapPoint",
    "EPMapAttributes",
    "ColormapModel",
    "ReportModel",
    "UserModel",
    "AttributeMetadata",
    # DB session
    "get_db_session",
    # Importer
    "import_carto",
    "import_studies",
    "discover_carto_exports",
    "get_filenames_from_csv",
    # Mesh parsing
    "read_carto_mesh",
]
