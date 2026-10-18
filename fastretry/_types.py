"""Shared type definitions for the retry package."""

from collections.abc import (
    Awaitable,
    Callable,
)
from concurrent.futures import (
    Executor,
)
from typing import (
    ReadOnly,
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
    attempts: ReadOnly[int | UnsetType]
    return_default_value: ReadOnly[R | UnsetType]
    delay: ReadOnly[Delay | UnsetType]
    jitter: ReadOnly[JitterStrategy | UnsetType]
    disable_logging: ReadOnly[bool | UnsetType]
    disable_warnings: ReadOnly[bool | UnsetType]
    retry_on: ReadOnly[RetryOnExceptionType | UnsetType]
    no_retry_on: ReadOnly[RetryOnExceptionType | UnsetType]
    callbacks: ReadOnly[RetryCallbacks | UnsetType | None]


class _RetryDefaultOptions(TypedDict, total=False):
    attempts: ReadOnly[int]
    delay: ReadOnly[Delay]
    disable_logging: ReadOnly[bool]
    disable_warnings: ReadOnly[bool]
    retry_on: ReadOnly[RetryOnExceptionType]
    no_retry_on: ReadOnly[RetryOnExceptionType]
    on_success: ReadOnly[CallbackType | None]
    on_retry: ReadOnly[CallbackType | None]
    on_failure: ReadOnly[CallbackType | None]
    jitter_for_exponential: ReadOnly[JitterStrategy]
    jitter_for_fixed: ReadOnly[JitterStrategy]
    sync_sleep_call: ReadOnly[Callable[[float], None]]
    async_sleep_call: ReadOnly[Callable[[float], Awaitable[None]]]


class _LoggingDefaultOptions(TypedDict, total=False):
    level_success: ReadOnly[LogLevel]
    level_retry: ReadOnly[LogLevel]
    level_failure: ReadOnly[LogLevel]
    level_sleep: ReadOnly[LogLevel]
    traceback_min_level: ReadOnly[LogLevel]


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
