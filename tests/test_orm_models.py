"""Verify registration of the PostgreSQL ORM models."""

from __future__ import annotations

from pulse_ep import (
    AttributeMetadata,
    Base,
    EPMapAttributes,
    EPMapModel,
    EPMapPoint,
    StudyModel,
    UserModel,
)


def test_models_are_registered_with_base() -> None:
    tables = Base.metadata.tables
    assert "studies" in tables
    # Other models are registered too — verify a representative subset.
    table_names = set(tables.keys())
    for model in (
        EPMapModel,
        EPMapAttributes,
        EPMapPoint,
        UserModel,
        AttributeMetadata,
        StudyModel,
    ):
        assert model.__tablename__ in table_names
