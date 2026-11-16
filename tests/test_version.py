"""Tests for the lazily resolved package version."""

import importlib
import importlib.metadata
from collections.abc import (
    Generator,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

import fastretry
from fastretry import (
    _version,
)


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def _reset_version_cache() -> Generator[None]:
    """Drop the cached version, so that every test resolves it on its own."""
    _version._resolve_version.cache_clear()

    yield

    _version._resolve_version.cache_clear()


def test_version_matches_installed_metadata() -> None:
    try:
        installed = importlib.metadata.version("fastretry")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - not installed
        pytest.skip("fastretry is not installed, so it has no metadata to compare with")

    assert fastretry.__version__ == installed


def test_version_falls_back_when_metadata_is_missing(mocker: MockerFixture) -> None:
    _ = mocker.patch.object(
        target=importlib.metadata,
        attribute="version",
        side_effect=importlib.metadata.PackageNotFoundError("fastretry"),
    )

    assert fastretry.__version__ == "0.0.0"


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
