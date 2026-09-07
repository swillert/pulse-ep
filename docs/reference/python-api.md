# Python API reference

The pulse-ep Python toolkit lives in `pulse_ep.core`. Common legacy entry points are re-exported from `pulse_ep`; vendor-neutral
fields, points, importers and operations are imported from their modules.

## Quick map

| Symbol                                              | Used for                                      |
| --------------------------------------------------- | --------------------------------------------- |
| [`EPMap`][pulse_ep.EPMap]                           | The central domain class: mesh + scalar fields. |
| [`Study`][pulse_ep.Study]                           | Container of `EPMap` instances.               |
| [`EPMapModel`][pulse_ep.EPMapModel]                 | ORM model for an EP map.                      |
| [`StudyModel`][pulse_ep.StudyModel]                 | ORM model for a study.                        |
| [`get_db_session`][pulse_ep.get_db_session]         | Transactional context manager.                |
| [`import_carto`][pulse_ep.import_carto]             | Import a single CARTO export.                 |
| [`import_studies`][pulse_ep.import_studies]         | Legacy batch import helper; prefer the current vendor CLIs.               |
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

## Vendor-neutral fields and measurements

::: pulse_ep.core.scalar_field.ScalarField
    options:
      heading_level: 3

::: pulse_ep.core.measurement.MeasurementPoint
    options:
      heading_level: 3

## Vendor import workflow

::: pulse_ep.core.importers.base
    options:
      members: [detect_vendor, get_importer, prepare_plan, commit_plan]
      heading_level: 3

::: pulse_ep.core.importers.source
    options:
      members: [source_for, DirSource, ZipSource, SevenZipSource]
      heading_level: 3

## Map comparison and interpolation

::: pulse_ep.core.comparison.compare_maps
    options:
      heading_level: 3

::: pulse_ep.core.interpolation
    options:
      members: [gaussian_interpolate, heat_interpolate]
      heading_level: 3
