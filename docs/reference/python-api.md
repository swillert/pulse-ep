# Python API reference

The pulse-ep Python toolkit lives in `pulse_ep.core`. The public surface
is re-exported from the top-level `pulse_ep` package — anything you
need for typical analyses is one `from pulse_ep import …` away.

## Quick map

| Symbol                                              | Used for                                      |
| --------------------------------------------------- | --------------------------------------------- |
| [`EPMap`][pulse_ep.EPMap]                           | The central domain class: mesh + scalar fields. |
| [`Study`][pulse_ep.Study]                           | Container of `EPMap` instances.               |
| [`EPMapModel`][pulse_ep.EPMapModel]                 | ORM model for an EP map.                      |
| [`StudyModel`][pulse_ep.StudyModel]                 | ORM model for a study.                        |
| [`get_db_session`][pulse_ep.get_db_session]         | Transactional context manager.                |
| [`import_carto`][pulse_ep.import_carto]             | Import a single CARTO export.                 |
| [`import_studies`][pulse_ep.import_studies]         | Import many studies from a CSV.               |
| [`read_carto_mesh`][pulse_ep.read_carto_mesh]       | Parse a CARTO `.mesh` text file.              |
| [`get_settings`][pulse_ep.core.config.get_settings] | Cached singleton of the typed settings.       |

## Top-level package

::: pulse_ep
    options:
      show_root_toc_entry: false
      members:
        - __version__
        - get_db_session
        - import_carto
        - import_studies
        - discover_carto_exports
        - get_filenames_from_csv
        - read_carto_mesh
      heading_level: 3

## Domain — `pulse_ep.core.epmap`

::: pulse_ep.core.epmap.EPMap
    options:
      heading_level: 3

## Domain — `pulse_ep.core.study`

::: pulse_ep.core.study.Study
    options:
      heading_level: 3

## Configuration — `pulse_ep.core.config`

::: pulse_ep.core.config
    options:
      show_root_toc_entry: false
      members:
        - Settings
        - get_settings
        - reset_settings
      heading_level: 3

## Database — `pulse_ep.core.database`

::: pulse_ep.core.database
    options:
      show_root_toc_entry: false
      members:
        - get_db_session
        - create_db_engine
        - init_db
        - seed_attribute_metadata
      heading_level: 3

## Importer — `pulse_ep.core.importer`

::: pulse_ep.core.importer
    options:
      show_root_toc_entry: false
      members:
        - import_carto
        - import_studies
        - discover_carto_exports
        - get_filenames_from_csv
      heading_level: 3

## Mesh processing — `pulse_ep.core.mesh_proc`

::: pulse_ep.core.mesh_proc
    options:
      show_root_toc_entry: false
      members:
        - read_carto_mesh_file
      heading_level: 3

## ORM models — `pulse_ep.core.models`

::: pulse_ep.core.models
    options:
      show_root_toc_entry: false
      members:
        - Base
        - StudyModel
        - EPMapModel
        - EPMapPoint
        - EPMapAttributes
        - ColormapModel
        - ReportModel
        - UserModel
        - AttributeMetadata
      heading_level: 3
      show_if_no_docstring: true
