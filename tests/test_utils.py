"""Tests for utility modules."""

from collections.abc import (
    Callable,
)
from typing import (
    Any,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

from retry._utils._function_types import (
    FunctionTypes,
)
from retry._utils._unset import (
    UNSET,
    UnsetType,
)
from retry._utils._warnings import (
    Warnings,
)


def test_repr() -> None:
    assert repr(UNSET) == "<unset>"


def test_singleton() -> None:
    assert UnsetType() is not UNSET


def test_warn(mocker: MockerFixture) -> None:
    mock_warn = mocker.patch("retry._utils._warnings._warnings.warn")
    w = Warnings(disable_warnings=False)
    w.warn("msg", stacklevel=2)
    mock_warn.assert_called_once_with("msg", stacklevel=2)


def test_disabled(mocker: MockerFixture) -> None:
    mock_warn = mocker.patch("retry._utils._warnings._warnings.warn")
    w = Warnings(disable_warnings=True)
    w.warn("msg", stacklevel=2)
    mock_warn.assert_not_called()


def test_simple_return() -> None:
    def fn() -> int:
        return 1

    ft = FunctionTypes(fn)
    assert ft._return_hint is int


def test_no_annotation() -> None:
    def fn():  # ruff: ignore[missing-return-type-private-function]
        return 1

    ft = FunctionTypes(fn)
    assert ft._return_hint is UNSET


def test_unresolvable() -> None:
    def fn() -> "NonExistent":  # ruff: ignore[undefined-name]
        return 1

    ft = FunctionTypes(fn)
    assert ft._return_hint is UNSET


def test_warn_mismatch(mocker: MockerFixture) -> None:
    def fn() -> int:
        return 1

    mock_warn = mocker.patch("retry._utils._warnings._warnings.warn")
    ft = FunctionTypes(fn)
    ft.warn_on_return_default_mismatch(
        return_default_value="str",
        disable_warnings=False,
    )
    mock_warn.assert_called_once()


def test_no_warn_match(mocker: MockerFixture) -> None:
    def fn() -> int:
        return 1

    mock_warn = mocker.patch("retry._utils._warnings._warnings.warn")
    ft = FunctionTypes(fn)
    ft.warn_on_return_default_mismatch(
        return_default_value=5,
        disable_warnings=False,
    )
    mock_warn.assert_not_called()


def test_no_warn_when_disabled(mocker: MockerFixture) -> None:
    def fn() -> int:
        return 1

    mock_warn = mocker.patch("retry._utils._warnings._warnings.warn")
    ft = FunctionTypes(fn)
    ft.warn_on_return_default_mismatch(
        return_default_value="str",
        disable_warnings=True,
    )
    mock_warn.assert_not_called()


def _make_fn(return_hint: object) -> Callable[..., object]:
    def fn() -> object:
        return None

    fn.__annotations__["return"] = return_hint
    return fn


@pytest.mark.parametrize(
    ("hint", "value", "expected"),
    [
        (int, 5, True),
        (int, "str", False),
        (int | str, "a", True),
        (int | str, 1.5, False),
        (list[int], [1], None),
        (list[int], "str", False),
        (dict[str, int], {"a": 1}, None),
        (Any, 5, None),
        (object, 5, None),
    ],
)
def test_matches_return_hint(hint: object, value: object, expected: bool | None) -> None:
    ft = FunctionTypes(_make_fn(hint))
    assert ft._matches_return_hint(value) is expected


def test_matches_return_hint_unset() -> None:
    def fn():  # ruff: ignore[missing-return-type-private-function]
        return 1

    ft = FunctionTypes(fn)
    assert ft._matches_return_hint(5) is None
