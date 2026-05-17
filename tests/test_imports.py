"""Smoke test: every name in the public API can be imported."""

from __future__ import annotations


def test_top_level_imports() -> None:
    from pulse_ep import (
        __version__,
        AttributeMetadata,
        Base,
        ColormapModel,
        EPMap,
        EPMapAttributes,
        EPMapModel,
        EPMapPoint,
        ReportModel,
        Study,
        StudyModel,
        UserModel,
        discover_carto_exports,
        get_db_session,
        get_filenames_from_csv,
        import_carto,
        import_studies,
        read_carto_mesh,
    )

    assert isinstance(__version__, str)
    _ = (
        AttributeMetadata,
        Base,
        ColormapModel,
        EPMap,
        EPMapAttributes,
        EPMapModel,
        EPMapPoint,
        ReportModel,
        Study,
        StudyModel,
        UserModel,
        discover_carto_exports,
        get_db_session,
        get_filenames_from_csv,
        import_carto,
        import_studies,
        read_carto_mesh,
    )


def test_core_subpackage_imports() -> None:
    from pulse_ep.core import (
        EPMap,
        EPMapModel,
        Study,
        process_xml,
        read_carto_mesh_file,
    )

    _ = (EPMap, EPMapModel, Study, process_xml, read_carto_mesh_file)


def test_examples_module_callable() -> None:
    from pulse_ep.examples.demo_synthetic import main

    assert callable(main)
