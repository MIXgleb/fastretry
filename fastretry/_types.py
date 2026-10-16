"""Shared type definitions for the retry package."""

from collections.abc import (
    Awaitable,
    Callable,
)
from concurrent.futures import (
    Executor,
)

from fastretry._compat.aliases import (
    RetryOnExceptionType,
)
from fastretry._compat.nodes import (
    TypedDict,
)
from fastretry._compat.sentinels import (
    UnsetType,
)
from fastretry._utils.callbacks import (
    CallbackType,
    RetryCallbacks,
)
from fastretry._utils.delay import (
    Delay,
    JitterStrategy,
)
from fastretry._utils.logs import (
    LogLevel,
)


class _RetryOptions[R](TypedDict, total=False):
    attempts: int | UnsetType
    return_default_value: R | UnsetType
    delay: Delay | UnsetType
    jitter: JitterStrategy | UnsetType
    disable_logging: bool | UnsetType
    disable_warnings: bool | UnsetType
    retry_on: RetryOnExceptionType | UnsetType
    no_retry_on: RetryOnExceptionType | UnsetType
    callbacks: RetryCallbacks | UnsetType | None


class _RetryDefaultOptions(TypedDict, total=False):
    attempts: int
    delay: Delay
    disable_logging: bool
    disable_warnings: bool
    retry_on: RetryOnExceptionType
    no_retry_on: RetryOnExceptionType
    on_success: CallbackType | None
    on_retry: CallbackType | None
    on_failure: CallbackType | None
    jitter_for_exponential: JitterStrategy
    jitter_for_fixed: JitterStrategy
    sync_sleep_call: Callable[[float], None]
    async_sleep_call: Callable[[float], Awaitable[None]]


class _LoggingDefaultOptions(TypedDict, total=False):
    level_success: LogLevel
    level_retry: LogLevel
    level_failure: LogLevel
    level_sleep: LogLevel
    traceback_min_level: LogLevel


class RetryKwargs[R](
    _RetryOptions[R],
    total=False,
    closed=True,
):
    """Keyword arguments accepted by :func:`~fastretry._retry.retry`."""


class RetryWithExecutorKwargs[R](
    _RetryOptions[R],
    total=False,
    closed=True,
):
    """Keyword arguments accepted by :func:`~fastretry._retry.retry_async`."""

    executor: Executor | UnsetType


class RetryDefaultsKwargs(
    _RetryDefaultOptions,
    total=False,
    closed=True,
):
    """Options accepted by :attr:`~fastretry._config.config.retry`."""


class LoggingDefaultsKwargs(
    _LoggingDefaultOptions,
    total=False,
    closed=True,
):
    """Options related to logging, configured via :attr:`~fastretry._config.config.logging`."""


class DefaultsKwargs(
    _RetryDefaultOptions,
    _LoggingDefaultOptions,
    total=False,
    closed=True,
):
    """All keyword arguments accepted by :data:`~fastretry._config.config`."""
