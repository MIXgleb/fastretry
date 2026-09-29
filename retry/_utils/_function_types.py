"""Runtime access to a function's declared type hints."""

import contextlib
import types
import typing
from typing import (
    TYPE_CHECKING,
    Any,
    Union,  # pyright: ignore[reportDeprecated]
)

from retry._utils._unset import (
    UNSET,
    UnsetType,
)
from retry._utils._warnings import (
    Warnings,
)

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
    )


_UNION: tuple[object, ...] = (Union, types.UnionType)  # pyright: ignore[reportDeprecated]
_UNCHECKABLE: tuple[object, ...] = (Any, object)


class FunctionTypes:
    """
    Best-effort runtime access to a function's declared type hints.

    Wraps ``typing.get_type_hints`` and provides helpers for inspecting
    and validating types. Only simple types, unions, and ``None`` are
    checked; generics are matched by their base class, and ``Any`` /
    ``object`` / unresolvable annotations are treated as inconclusive.

    Parameters
    ----------
    func : Callable[..., Any]
        Function whose declared type hints are used as the reference.

    """

    __slots__ = ("_func", "_return_hint")

    def __init__(self, func: Callable[..., Any]) -> None:
        self._func = func
        self._return_hint = self._extract_return_hint()

    def warn_on_return_default_mismatch(
        self,
        *,
        return_default_value: object,
        disable_warnings: bool,
    ) -> None:
        """
        Warn if ``return_default_value`` doesn't match the declared return type.

        The check is best-effort: only simple types, unions, and ``None``
        are verified. Generic hints (``list[int]``, ``dict[str, str]``),
        ``Any``, ``object``, and unresolvable annotations are skipped
        silently.

        Parameters
        ----------
        return_default_value : object
            Value that will be returned on failure.
        disable_warnings : bool
            If ``True``, warnings are suppressed.

        """
        if self._matches_return_hint(return_default_value) is False:
            Warnings(disable_warnings=disable_warnings).warn(
                f"\n\treturn_default_value {return_default_value!r} does not match "
                f"the declared return type {self._return_hint!r} "
                f"of '{getattr(self._func, '__qualname__', '<anonymous>')}'.\n\t"
                f"Set return_default_value to a value compatible with the function's "
                f"return type to avoid returning an unexpected type.",
                stacklevel=6,
            )

    def _extract_return_hint(self) -> Any | UnsetType:  # ruff: ignore[any-type]
        """
        Best-effort extraction of the declared return type of the function.

        Returns
        -------
        Any | UnsetType
            Resolved return annotation, or ``UNSET`` if it cannot be obtained.

        """
        with contextlib.suppress(Exception):
            hints = typing.get_type_hints(self._func)
            return hints.get("return", UNSET)
        return UNSET

    def _unwrap_return_hint(self) -> tuple[Any, ...]:
        """
        Flatten a union hint into a tuple of member types.

        Non-union hints produce a single-element tuple. ``Optional[T]`` and
        ``T | None`` are unions and produce ``(T, NoneType)``.

        Returns
        -------
        tuple[Any, ...]
            Member types of the union, or the hint itself as a single element.

        """
        return (
            typing.get_args(self._return_hint)
            if typing.get_origin(self._return_hint) in _UNION
            else (self._return_hint,)
        )

    def _matches_return_hint(self, value: object) -> bool | None:
        """
        Check whether ``value`` matches the function's declared return type.

        Parameters
        ----------
        value : object
            Value to check against the declared return type.

        Returns
        -------
        bool | None
            ``True`` if ``value`` matches the hint or one of its union members.
            ``False`` if it matches none of them and the hint is fully checkable.
            ``None`` if the check is inconclusive: the hint is ``UNSET``,
                contains ``Any``/``object``, or is a generic whose
                type arguments cannot be verified at runtime.

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
