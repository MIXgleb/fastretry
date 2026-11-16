"""Tests for the lazily resolved package version."""

import importlib
import importlib.metadata

import pytest
from pytest_mock import (
    MockerFixture,
)

import fastretry


def test_version_matches_installed_metadata() -> None:
    assert fastretry.__version__ == importlib.metadata.version("fastretry")


def test_version_is_resolved_once(mocker: MockerFixture) -> None:
    expected = fastretry.__version__
    _ = mocker.patch.object(
        target=importlib.metadata,
        attribute="version",
        side_effect=AssertionError("version is resolved again"),
    )

    assert fastretry.__version__ == expected


def test_missing_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="module 'fastretry' has no attribute 'nope'"):
        _ = fastretry.nope


def test_import_does_not_resolve_version(mocker: MockerFixture) -> None:
    spy = mocker.patch.object(importlib.metadata, "version")

    _ = importlib.reload(fastretry)

    spy.assert_not_called()


def test_import_does_not_import_metadata() -> None:
    names = vars(fastretry)

    assert "importlib" not in names
    assert "metadata" not in names
