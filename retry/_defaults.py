"""
Global configuration for retry defaults and logging.

All default values used by ``BaseRetrying`` live in a single
:class:`_Defaults` instance. Public functions in this module mutate that
instance, changing the behaviour of all subsequently created retry
decorators.

Configuration is split into two groups:

- **Retry defaults** (:func:`set_retry_defaults`) — options that can also
  be passed per-decorator via ``@retry(...)``.
- **Global options** (:func:`configure_retry`) — application-wide settings
  that cannot be passed per-decorator.

Loggers are configured separately via :func:`configure_logging`.
"""

import asyncio
import contextlib
import dataclasses as dc
import time
from collections.abc import (
    Awaitable,
    Callable,
    Generator,
)
from typing import (
    Final,
    Unpack,
    final,
)

from retry._types import (
    DefaultsKwargs,
    GlobalKwargs,
    LocalKwargs,
    LoggingKwargs,
)
from retry._utils import (
    Delay,
    JitterStrategy,
    LogLevel,
    RetryStats,
    UnsetType,
    default_on_failure,
    default_on_retry,
    default_on_success,
)


@dc.dataclass(slots=True)
class _Defaults:
    # --- retry options (per-decorator, with global defaults) ---
    attempts: int = 1
    delay: Delay = 0
    disable_logging: bool = False
    disable_warnings: bool = False
    on_success: Callable[[RetryStats], None] | None = default_on_success
    on_retry: Callable[[RetryStats], None] | None = default_on_retry
    on_failure: Callable[[RetryStats], None] | None = default_on_failure

    # --- global options (application-wide) ---
    jitter_for_exponential: JitterStrategy = "none"
    jitter_for_fixed: JitterStrategy = "none"

    sync_sleep_call: Callable[[float], None] = time.sleep
    async_sleep_call: Callable[[float], Awaitable[None]] = asyncio.sleep

    # --- logging ---
    level_success: LogLevel = LogLevel.OFF
    level_retry: LogLevel = LogLevel.WARNING
    level_failure: LogLevel = LogLevel.ERROR
    level_sleep: LogLevel = LogLevel.OFF

    traceback_min_level: LogLevel = LogLevel.ERROR

    @final
    def set(self, **kwargs: Unpack[DefaultsKwargs]) -> None:
        """
        Set one or more defaults by name.

        Values equal to :data:`~._types.UNSET` are ignored.

        Raises
        ------
        AttributeError
            Unknown default key

        """
        for key, value in kwargs.items():
            if isinstance(value, UnsetType):
                continue

            if not hasattr(self, key):
                msg = f"Unknown default: {key!r}"
                raise AttributeError(msg)

            setattr(self, key, value)

    @final
    def reset(self) -> None:
        """Reset all defaults to their factory values."""
        fresh = type(self)()

        for f in dc.fields(self):
            setattr(self, f.name, getattr(fresh, f.name))


defaults: Final[_Defaults] = _Defaults()


def configure_logging(**kwargs: Unpack[LoggingKwargs]) -> None:
    """
    Configure logging for the retry decorators.

    Logging is handled by the standard :mod:`logging` module through a
    single logger named ``"retry"``, which writes to stdout by default.

    Each log kind has its own level. Set a level to :attr:`LogLevel.OFF`
    to disable that kind.

    Parameters
    ----------
    level_success : LogLevel, optional
        Level for messages emitted after a successful attempt,
        by default :attr:`LogLevel.OFF`.
    level_retry : LogLevel, optional
        Level for messages emitted after a failed attempt, before
        sleeping, by default :attr:`LogLevel.WARNING`.
    level_failure : LogLevel, optional
        Level for messages emitted after all attempts have failed,
        by default :attr:`LogLevel.ERROR`.
    level_sleep : LogLevel, optional
        Level for messages emitted before sleeping between attempts,
        by default :attr:`LogLevel.OFF`.
    traceback_min_level : LogLevel, optional
        Minimum level at which a traceback is attached to the log record.
        Messages below this level are logged without traceback,
        by default :attr:`LogLevel.ERROR`.

    """
    defaults.set(**kwargs)


def set_retry_defaults(**kwargs: Unpack[LocalKwargs]) -> None:
    """
    Override default retry options.

    These options can also be passed per-decorator via ``@retry(...)``.
    Each parameter, if provided, replaces the corresponding factory
    default for all subsequently created retry decorators. Per-decorator
    values take precedence over these defaults.

    Parameters
    ----------
    attempts : int, optional
        Default number of attempts, by default 1
    delay : Delay, optional
        Default delay between attempts, in seconds, by default 0
    disable_logging : bool, optional
        Disable all logging, by default False
    disable_warnings : bool, optional
        Disable all warnings, by default False
    on_success : Callable[[RetryStats], None] | None, optional
        Default callback invoked after a successful attempt. Pass
        ``None`` to disable it. When omitted, no callback is invoked.
    on_retry : Callable[[RetryStats], None] | None, optional
        Default callback invoked after a failed attempt, before sleeping.
        Pass ``None`` to disable it. When omitted, the built-in default
        is used.
    on_failure : Callable[[RetryStats], None] | None, optional
        Default callback invoked after all attempts have failed. Pass
        ``None`` to disable it. When omitted, the built-in default is
        used.

    """
    defaults.set(**kwargs)


def configure_retry(**kwargs: Unpack[GlobalKwargs]) -> None:
    """
    Configure application-wide retry options.

    These options cannot be passed per-decorator and apply to all
    subsequently created retry decorators.

    Parameters
    ----------
    jitter_for_exponential : JitterStrategy, optional
        Default jitter strategy for exponential delay, by default "none"
    jitter_for_fixed : JitterStrategy, optional
        Default jitter strategy for fixed delay, by default "none"
    sync_sleep_call : Callable[[float], None], optional
        Sync function used to sleep between attempts,
        by default ``time.sleep``
    async_sleep_call : Callable[[float], Awaitable[None]], optional
        Async function used to sleep between attempts,
        by default ``asyncio.sleep``

    """
    defaults.set(**kwargs)


def reset_defaults() -> None:
    """
    Reset all defaults to their factory values.

    Useful in tests to avoid leaking configuration between test cases.
    """
    defaults.reset()


@contextlib.contextmanager
def temporary_defaults(**kwargs: Unpack[DefaultsKwargs]) -> Generator[None]:
    """
    Temporarily override defaults, restoring them on exit.

    Useful in tests: the previous values are restored even if the
    body raises.

    Parameters
    ----------
    **kwargs : Unpack[DefaultsKwargs]
        Defaults to override for the duration of the block.

    Yields
    ------
    None
        Control to the caller.

    """
    snapshot = {f.name: getattr(defaults, f.name) for f in dc.fields(defaults)}
    defaults.set(**kwargs)

    try:
        yield
    finally:
        for name, value in snapshot.items():
            setattr(defaults, name, value)
