"""Runtime validation of ``return_default_value`` against a function's return type."""

import contextlib
import types
import typing

from retry._types import (
    UNSET,
    UnsetType,
)
from retry._utils._warnings import (
    warning,
)

if typing.TYPE_CHECKING:
    from collections.abc import (
        Callable,
    )


_UNION: tuple[object, ...] = (typing.Union, types.UnionType)  # pyright: ignore[reportDeprecated]
_UNCHECKABLE: tuple[object, ...] = (typing.Any, object)


class ReturnTypeChecker:
    """
    Best-effort runtime check that a value matches a function's return type.

    Only simple types, unions, and ``None`` are verified. Generic hints
    (``list[int]``, ``dict[str, str]``) are matched by their base class
    only; ``Any``, ``object``, and unresolvable annotations are treated
    as inconclusive.

    Parameters
    ----------
    func : Callable[..., Any]
        Function whose declared return type is used as the reference.

    """

    __slots__ = ("_func", "_hint")

    def __init__(self, func: Callable[..., typing.Any]) -> None:
        self._func = func
        self._hint = self._extract_return_hint()

    def _extract_return_hint(self) -> typing.Any | UnsetType:  # ruff: ignore[any-type]
        """
        Best-effort extraction of the declared return type of ``func``.

        Returns
        -------
        Any | UnsetType
            Resolved return annotation, or ``UNSET`` if it cannot be obtained.

        """
        with contextlib.suppress(Exception):
            hints = typing.get_type_hints(self._func)
            return hints.get("return", UNSET)
        return UNSET

    def _unwrap_union(self) -> tuple[typing.Any, ...]:
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
            typing.get_args(self._hint)
            if typing.get_origin(self._hint) in _UNION
            else (self._hint,)
        )

    def _matches(self, default_value: object) -> bool | None:
        """
        Check whether ``value`` matches the function's declared return type.

        Parameters
        ----------
        default_value : object
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
        if isinstance(self._hint, UnsetType):
            return None

        has_any_or_generic = False

        for member in self._unwrap_union():
            if member in _UNCHECKABLE:
                has_any_or_generic = True
                continue

            if (origin := typing.get_origin(member)) is not None:
                if isinstance(default_value, origin):
                    has_any_or_generic = True
                continue

            if isinstance(member, type) and isinstance(default_value, member):
                return True

        if has_any_or_generic:
            return None
        return False

    def warn_on_return_default_mismatch(
        self,
        *,
        default_value: object,
        disable_warnings: bool,
    ) -> None:
        """
        Emit a warning if ``default_value`` doesn't match the declared return type of ``func``.

        The check is best-effort: only simple types, unions, and ``None`` are
        verified. Generic hints (``list[int]``, ``dict[str, str]``), ``Any``,
        ``object``, and unresolvable annotations are skipped silently.

        Parameters
        ----------
        default_value : object
            Value that will be returned on failure
        disable_warnings : bool, optional
            Disable all warnings

        """
        if self._matches(default_value) is False:
            warning(
                f"\n\treturn_default_value {default_value!r} does not match "
                f"the declared return type {self._hint!r} of '{self._func.__qualname__}'.\n\t"
                f"Set return_default_value to a value compatible with the function's "
                f"return type to avoid returning an unexpected type.",
                stacklevel=4,
                disable_warnings=disable_warnings,
            )
