"""Shared type definitions for the retry package."""

from collections.abc import (
    Awaitable,
    Callable,
)
from concurrent.futures import (
    Executor,
)
from typing import (
    TypedDict,
)

from retry._utils import (
    CallbackType,
    Delay,
    JitterStrategy,
    LogLevel,
    RetryCallbacks,
    UnsetType,
)


class RetryOptions(TypedDict, total=False):
    """
    Options accepted by ``@retry(...)``.

    These options are also stored as global retry defaults via
    :attr:`~retry._config.config.retry`.

    All keys are optional. Missing keys fall back to the values in
    :data:`~retry._defaults.global_defaults`.
    """

    attempts: int | UnsetType
    delay: Delay | UnsetType
    disable_logging: bool | UnsetType
    disable_warnings: bool | UnsetType
    retry_on: type[BaseException] | tuple[type[BaseException], ...] | UnsetType
    no_retry_on: type[BaseException] | tuple[type[BaseException], ...] | UnsetType


class RetryKwargs[R](RetryOptions, total=False):
    """Keyword arguments accepted by :func:`~retry._retry.retry`."""

    return_default_value: R | UnsetType
    jitter: JitterStrategy | UnsetType
    callbacks: RetryCallbacks | UnsetType | None


class RetryWithExecutorKwargs[R](RetryKwargs[R], total=False):
    """Keyword arguments accepted by :func:`~retry._retry.retry_async`."""

    executor: Executor | UnsetType


class RetryDefaultsKwargs(
    RetryOptions,
    total=False,
):
    """Options accepted by :attr:`~retry._config.config.retry`."""

    on_success: CallbackType | None
    on_retry: CallbackType | None
    on_failure: CallbackType | None
    jitter_for_exponential: JitterStrategy
    jitter_for_fixed: JitterStrategy
    sync_sleep_call: Callable[[float], None]
    async_sleep_call: Callable[[float], Awaitable[None]]


class LoggingKwargs(
    TypedDict,
    total=False,
):
    """Options related to logging, configured via :attr:`~retry._config.config.logging`."""

    level_success: LogLevel
    level_retry: LogLevel
    level_failure: LogLevel
    level_sleep: LogLevel
    traceback_min_level: LogLevel


class DefaultsKwargs(
    RetryDefaultsKwargs,
    LoggingKwargs,
    total=False,
):
    """All keyword arguments accepted by :data:`~retry._config.config`."""
