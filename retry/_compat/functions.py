"""Runtime helpers for inspecting callables."""

import contextlib
import inspect
import types
import typing
from collections.abc import (
    Callable,
)
from typing import (
    Any,
    Union,  # pyright: ignore[reportDeprecated]
)

from retry._compat.aliases import (
    CoroType,
)
from retry._compat.nodes import (
    TypeIs,
)
from retry._compat.sentinels import (
    UNSET,
    UnsetType,
)

_UNION: tuple[object, ...] = (Union, types.UnionType)  # pyright: ignore[reportDeprecated]
_UNCHECKABLE: tuple[object, ...] = (Any, object)


def is_coroutine_function[**P, R](
    func: Callable[P, R] | Callable[P, CoroType[R]],
) -> TypeIs[Callable[P, CoroType[R]]]:
    """
    Check whether ``func`` is a coroutine function.

    Parameters
    ----------
    func : Callable[P, R] | Callable[P, CoroutineType[Any, Any, R]]
        Callable to check.

    Returns
    -------
    TypeIs[Callable[P, CoroutineType[Any, Any, R]]]
        ``True`` if ``func`` is a coroutine function.

    """
    return inspect.iscoroutinefunction(func)


class TypeChecker:
    """
    Best-effort inspection of a callable's declared type hints.

    Only simple types, unions, and ``None`` are checked; generics,
    ``Any``, ``object``, and unresolvable annotations are treated as
    inconclusive.

    Parameters
    ----------
    func : Callable[..., Any]
        Callable whose declared type hints are used as the
        reference.

    """

    __slots__ = ("_func", "_return_hint")

    def __init__(
        self,
        func: Callable[..., Any],
    ) -> None:
        self._func = func
        self._return_hint = self._extract_return_hint()

    def matches_return_hint(
        self,
        value: object,
    ) -> bool | None:
        """
        Check whether ``value`` matches the declared return type.

        Parameters
        ----------
        value : object
            Value to check against the declared return type.

        Returns
        -------
        bool | None
            - ``True`` if the value matches.
            - ``False`` if it does not and the hint is fully checkable.
            - ``None`` if the check is inconclusive.

        """
        if isinstance(self._return_hint, UnsetType):
            return None

        has_any_or_generic = False

        for member in self._unwrap_return_hint():
            if member in _UNCHECKABLE:
                has_any_or_generic = True
                continue

            if (origin := typing.get_origin(member)) is not None:
                if isinstance(value, origin):
                    has_any_or_generic = True
                continue

            if isinstance(member, type) and isinstance(value, member):
                return True

        if has_any_or_generic:
            return None
        return False

    @property
    def return_hint(self) -> object:
        """
        Resolved return annotation of the wrapped callable.

        Returns
        -------
        Any | UnsetType
            Resolved return hint, or ``UNSET`` if it cannot be obtained.

        """
        return self._return_hint

    def _extract_return_hint(self) -> Any | UnsetType:  # ruff: ignore[any-type]
        with contextlib.suppress(Exception):
            hints = typing.get_type_hints(self._func)
            return hints.get("return", UNSET)
        return UNSET

    def _unwrap_return_hint(self) -> tuple[Any, ...]:
        return (
            typing.get_args(self._return_hint)
            if typing.get_origin(self._return_hint) in _UNION
            else (self._return_hint,)
        )
