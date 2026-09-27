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
    Literal,
    NamedTuple,
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


type LogLevel = Literal["info", "warning", "error"]
type Delay = float | ExponentialDelay
type JitterStrategy = Literal["full", "equal", "decorrelated", "none"]


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


class LogContext(Protocol):
    """
    Interface for objects that expose logging configuration.

    Implemented by ``BaseRetrying``. Any object with these attributes can
    be passed to :class:`Log`.
    """

    logger_info: LoggerType | None
    logger_warning: LoggerType | None
    logger_error: LoggerType | None
    logger_traceback_kwarg: str
    disable_logging: bool
    disable_info_logging: bool
    disable_warning_logging: bool
    disable_error_logging: bool
    include_traceback_in_warning_log: bool
    include_traceback_in_error_log: bool
    disable_warnings: bool


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
    delay: Delay | UnsetType
    disable_logging: bool | UnsetType
    disable_warnings: bool | UnsetType


class RetryKwargs[R](
    RetryOptions,
    total=False,
):
    """Keyword arguments accepted by :func:`~.retry.retry`."""

    return_default_value: R | UnsetType
    jitter: JitterStrategy | UnsetType


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
    jitter_for_exponential: JitterStrategy | UnsetType
    jitter_for_fixed: JitterStrategy | UnsetType
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
    logger_traceback_kwarg: str | UnsetType


class DefaultsKwargs(
    RetryOptions,
    GlobalKwargs,
    LoggingKwargs,
    total=False,
):
    """All keyword arguments accepted by :meth:`_Defaults.set`."""


class ExponentialDelay(NamedTuple):
    """
    Exponential backoff configuration.

    The effective delay for attempt ``n`` (1-based) is::

        delay * backoff_factor ** (n - 1)

    capped at ``max_delay`` when it is set.

    Parameters
    ----------
    delay : float
        Base delay in seconds. Must be positive.
    backoff_factor : float, optional
        Multiplier applied on each subsequent attempt, by default 2.0.
        Values ``<= 1.0`` effectively disable exponential growth.
    max_delay : float | None, optional
        Upper bound for the computed delay, by default None (no cap).
        Must be positive when set.

    """

    delay: float
    backoff_factor: float = 2.0
    max_delay: float | None = None
