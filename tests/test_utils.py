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

from fastretry._compat.functions import (
    TypeChecker,
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


def test_simple_return() -> None:
    def fn() -> int:
        return 1

    ft = TypeChecker(fn)
    assert ft._return_hint is int
    assert fn() == 1


def test_no_annotation() -> None:
    def fn():  # ruff: ignore[missing-return-type-private-function]
        return 1

    ft = TypeChecker(fn)
    assert ft._return_hint is UNSET
    assert fn() == 1


def test_unresolvable() -> None:
    def fn() -> "NonExistent":  # ruff: ignore[undefined-name]
        return 1

    ft = TypeChecker(fn)
    assert ft._return_hint is UNSET
    assert fn() == 1


def test_warn_mismatch() -> None:
    def fn() -> int:
        return 1

    ft = TypeChecker(fn)
    assert ft.matches_return_hint("str") is False
    assert fn() == 1


def test_no_warn_match() -> None:
    def fn() -> int:
        return 1

    ft = TypeChecker(fn)
    assert ft.matches_return_hint(5) is True
    assert fn() == 1


def test_no_warn_when_disabled() -> None:
    def fn() -> Any:  # ruff: ignore[any-type]
        return 1

    ft = TypeChecker(fn)
    assert ft.matches_return_hint(int) is None
    assert fn() == 1


def _make_fn(return_hint: object) -> Callable[..., object]:
    def fn() -> object:
        return None

    assert fn() is None

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
    ft = TypeChecker(_make_fn(hint))
    assert ft.matches_return_hint(value) is expected


def test_matches_return_hint_unset() -> None:
    def fn():  # ruff: ignore[missing-return-type-private-function]
        return 1

    ft = TypeChecker(fn)
    assert ft.matches_return_hint(5) is None
    assert fn() == 1
