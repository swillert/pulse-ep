"""Core domain, persistence, and CARTO ingestion for pulse-ep.

Public API exported here is considered stable; everything else inside the
sub-modules should be treated as implementation detail and may change
without notice.
"""

from __future__ import annotations

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.study import Study

from pulse_ep.core.models import (
    Base,
    StudyModel,
    EPMapModel,
    EPMapPoint,
    EPMapAttributes,
    ColormapModel,
    ReportModel,
    UserModel,
    AttributeMetadata,
)

from pulse_ep.core.database import get_db_session

from pulse_ep.core.importer import (
    import_carto,
    import_studies,
    discover_carto_exports,
    get_filenames_from_csv,
)

from pulse_ep.core.mesh_proc import read_carto_mesh_file
from pulse_ep.core.xml_proc import (
    process_xml,
    get_maps,
    get_study_name,
)

__all__ = [
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
    # Mesh / XML parsing
    "read_carto_mesh_file",
    "process_xml",
    "get_maps",
    "get_study_name",
]
