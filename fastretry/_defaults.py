"""Global configuration for retry defaults and logging."""

import asyncio
import contextvars
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

from retry._compat.aliases import (
    RetryOnExceptionType,
)
from retry._types import (
    DefaultsKwargs,
)
from retry._utils.callbacks import (
    CallbackType,
    default_on_failure,
    default_on_retry,
    default_on_success,
)
from retry._utils.delay import (
    Delay,
    JitterStrategy,
)
from retry._utils.logs import (
    LogLevel,
)


@dc.dataclass(slots=True)
class _Defaults:
    """Container for all default values."""

    # --- retry options (per-decorator, with global defaults) ---
    attempts: int = 1
    delay: Delay = 0
    disable_logging: bool = False
    disable_warnings: bool = False
    on_success: CallbackType | None = default_on_success
    on_retry: CallbackType | None = default_on_retry
    on_failure: CallbackType | None = default_on_failure
    retry_on: RetryOnExceptionType = Exception
    no_retry_on: RetryOnExceptionType = ()

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
    def set(
        self,
        **kwargs: Unpack[DefaultsKwargs],
    ) -> None:
        """
        Set one or more defaults by name.

        Raises
        ------
        AttributeError
            Unknown default key

        """
        all_keys = {f.name for f in dc.fields(self)}

        for key, value in kwargs.items():
            if key not in all_keys:
                msg = f"Unknown default: {key!r}"
                raise AttributeError(msg)

            setattr(self, key, value)

    @final
    def reset(self) -> None:
        """Reset all defaults to their factory values."""
        fresh = type(self)()

        for f in dc.fields(self):
            setattr(self, f.name, getattr(fresh, f.name))


global_defaults: Final[_Defaults] = _Defaults()
context_defaults: contextvars.ContextVar[_Defaults | None] = contextvars.ContextVar(
    "retry_defaults",
    default=None,
)


def get_defaults() -> _Defaults:
    """
    Return the effective defaults for the current context.

    Returns
    -------
    _Defaults
        Effective defaults for the current context.

    """
    current_defaults = context_defaults.get()
    return current_defaults if current_defaults is not None else global_defaults
