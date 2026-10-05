"""
Global configuration for retry defaults and logging.

All default values used by :class:`~retry.base.BaseRetrying`
live in a single :class:`~retry._defaults._Defaults` instance.
Public functions in the :mod:`~retry._config` module mutate
that instance, changing the behaviour of all subsequently
created retry decorators.

Configuration is split into two groups:

- **Retry defaults** — options that can also be passed per-decorator
via ``@retry(...)``.
- **Logging configuration** — log levels and traceback thresholds.

Both are configured via :data:`~retry._config.config`.
"""

import asyncio
import dataclasses as dc
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Final,
    Unpack,
    final,
)

from retry._types import (
    DefaultsKwargs,
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

        Values equal to ``UNSET`` are ignored.

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
