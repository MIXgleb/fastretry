"""Shared type definitions for the retry package."""

from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    TypedDict,
)

from retry._utils import (
    Delay,
    JitterStrategy,
    LogLevel,
    RetryCallbacks,
    RetryStats,
    UnsetType,
)


class RetryOptions(TypedDict, total=False):
    """
    Options accepted by ``@retry(...)``.

    These options are also stored as global retry defaults via
    :func:`~._defaults.set_retry_defaults`.

    All keys are optional. Missing keys fall back to the values in
    :data:`~._defaults.defaults`.
    """

    attempts: int | UnsetType
    delay: Delay | UnsetType
    disable_logging: bool | UnsetType
    disable_warnings: bool | UnsetType


class RetryKwargs[R](RetryOptions, total=False):
    """Keyword arguments accepted by :func:`~.retry.retry`."""

    return_default_value: R | UnsetType
    jitter: JitterStrategy | UnsetType
    callbacks: RetryCallbacks | UnsetType


class LocalKwargs(RetryOptions, total=False):
    """
    Options accepted by ``@retry(...)``.

    These options are also stored as global retry defaults via
    :func:`~._defaults.set_retry_defaults`.
    """

    on_success: Callable[[RetryStats], None] | None
    on_retry: Callable[[RetryStats], None] | None
    on_failure: Callable[[RetryStats], None] | None


class GlobalKwargs(TypedDict, total=False):
    """
    Options that exist only in :data:`~._defaults.defaults`, not in :class:`~.base.BaseRetrying`.

    These are configured application-wide via
    :func:`~._defaults.configure_retry`.
    """

    jitter_for_exponential: JitterStrategy
    jitter_for_fixed: JitterStrategy
    sync_sleep_call: Callable[[float], None]
    async_sleep_call: Callable[[float], Awaitable[None]]


class LoggingKwargs(
    TypedDict,
    total=False,
):
    """Options related to logging, configured via :func:`~._defaults.configure_logging`."""

    level_success: LogLevel
    level_retry: LogLevel
    level_failure: LogLevel
    level_sleep: LogLevel
    traceback_min_level: LogLevel


class DefaultsKwargs(
    LocalKwargs,
    GlobalKwargs,
    LoggingKwargs,
    total=False,
):
    """All keyword arguments accepted by :meth:`~._defaults._Defaults.set`."""
