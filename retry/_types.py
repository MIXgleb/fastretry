"""
Shared type definitions for the retry package.

This module contains type aliases, type variables, protocols, and the
``UnsetType`` sentinel used across the package to distinguish
"no value provided" from an explicit ``None``.
"""

from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Protocol,
    TypedDict,
    final,
    override,
)

if TYPE_CHECKING:
    from collections.abc import (
        Awaitable,
        Callable,
    )


@final
class UnsetType:
    """
    Sentinel type meaning "no value provided".

    Used instead of ``None`` to distinguish "user did not pass anything"
    from "user explicitly passed ``None``" (which may be a valid value,
    e.g. for ``return_default_value``).
    """

    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return "<unset>"


UNSET: Final[UnsetType] = UnsetType()


class LoggerType(Protocol):
    """
    Signature of a logger callable.

    Accepts optional positional ``%``-style arguments,
    and arbitrary keyword arguments (e.g. ``exc_info``).
    """

    def __call__(self, *args: Any, **kwargs: Any) -> None:  # ruff: ignore[any-type]
        """Call the logger with an optional %-style format."""


class RetryOptions(
    TypedDict,
    total=False,
):
    """
    Options accepted by ``@retry(...)``.

    These options are also stored as global retry defaults via
    :func:`~._config.set_retry_defaults`.

    All keys are optional. Missing keys fall back to the values in
    :data:`~._config.defaults`.
    """

    attempts: int | UnsetType
    delay: float | UnsetType
    disable_all_logging: bool | UnsetType
    re_raise_exception: bool | UnsetType


class ReturnDefaultValueOption[R](
    TypedDict,
    total=False,
):
    """The ``return_default_value`` option, generic over the return type."""

    return_default_value: R | UnsetType


class RetryKwargs[R](
    RetryOptions,
    ReturnDefaultValueOption[R],
    total=False,
):
    """Keyword arguments accepted by :func:`~.retry.retry`."""


class LocalKwargs(
    RetryOptions,
    total=False,
):
    """
    Options accepted by ``@retry(...)``.

    These options are also stored as global retry defaults via
    :func:`~._config.set_retry_defaults`.
    """


class GlobalKwargs(
    TypedDict,
    total=False,
):
    """
    Options that exist only in :data:`~._config.defaults`, not in :class:`~.base.BaseRetrying`.

    These are configured application-wide via
    :func:`~._config.configure_retry`.
    """

    disable_info_logging: bool | UnsetType
    disable_warning_logging: bool | UnsetType
    disable_error_logging: bool | UnsetType
    include_traceback_in_warning_log: bool | UnsetType
    include_traceback_in_error_log: bool | UnsetType
    sync_sleep_call: Callable[[float], None] | UnsetType
    async_sleep_call: Callable[[float], Awaitable[None]] | UnsetType


class LoggingKwargs(
    TypedDict,
    total=False,
):
    """Options related to logging, configured via :func:`~._config.configure_logging`."""

    logger_info: LoggerType | UnsetType | None
    logger_warning: LoggerType | UnsetType | None
    logger_error: LoggerType | UnsetType | None
    exc_info_kwarg: str | UnsetType


class DefaultsKwargs(
    RetryOptions,
    GlobalKwargs,
    LoggingKwargs,
    total=False,
):
    """All keyword arguments accepted by :meth:`_Defaults.set`."""
