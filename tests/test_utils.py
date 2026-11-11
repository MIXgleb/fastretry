"""Tests for utility modules."""

from pytest_mock import (
    MockerFixture,
)

from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._utils.warnings import (
    Warnings,
)


def test_repr() -> None:
    assert repr(UNSET) == "<unset>"


def test_singleton() -> None:
    assert UnsetType() is not UNSET


def test_warn(mocker: MockerFixture) -> None:
    mock_warn = mocker.patch("fastretry._utils.warnings._warnings.warn")
    w = Warnings(disable_warnings=False)
    w.warn("msg", stacklevel=2)
    mock_warn.assert_called_once_with("msg", stacklevel=2)


def test_disabled(mocker: MockerFixture) -> None:
    mock_warn = mocker.patch("fastretry._utils.warnings._warnings.warn")
    w = Warnings(disable_warnings=True)
    w.warn("msg", stacklevel=2)
    mock_warn.assert_not_called()
