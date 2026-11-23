"""Global configuration for retry defaults and logging."""

import contextvars
import dataclasses as dc
from typing import (
    Final,
    Unpack,
    final,
)

from fastretry._compat.aliases import (
    RetryOnExceptionType,
)
from fastretry._compat.types import (
    DefaultsKwargs,
)
from fastretry._utils.callbacks import (
    CallbackType,
    default_on_failure,
    default_on_retry,
    default_on_success,
)
from fastretry._utils.delays import (
    Delay,
    JitterStrategy,
)
from fastretry._utils.logs import (
    LogLevel,
)
from fastretry._utils.shared_loop import (
    AsyncCallbackMode,
)


@dc.dataclass(slots=True)
class Defaults:
    """
    Container for all default values.

    A fresh instance is created by :attr:`config.context` for every block,
    so writing to a context instance never affects the process-wide one.

    Attributes
    ----------
    attempts : int
        Default number of attempts, 1 by default.
    delay : Delay
        Default delay between attempts, 0 by default.
    disable_logging : bool
        If ``True``, logging is disabled for every decorator, by default False.
    disable_warnings : bool
        If ``True``, warnings are suppressed for every decorator, by default False.
    on_success : CallbackType | None
        Default callback invoked after a successful attempt.
    on_retry : CallbackType | None
        Default callback invoked after a failed attempt, before sleeping.
    on_failure : CallbackType | None
        Default callback invoked after all attempts have failed.
    retry_on : RetryOnExceptionType
        Exception types that trigger a retry, ``Exception`` by default.
    no_retry_on : RetryOnExceptionType
        Exception types that are never retried, ``()`` by default.
    jitter_for_exponential : JitterStrategy
        Jitter strategy used when the delay is an
        :class:`~fastretry.delays.ExponentialDelay`, ``"none"`` by default.
    jitter_for_fixed : JitterStrategy
        Jitter strategy used for a fixed or custom delay, ``"none"`` by default.
    async_callback_mode : AsyncCallbackMode
        How async callbacks of synchronous functions are dispatched,
        ``"thread_per_call"`` by default.
    unwrap_single_exception : bool
        If ``True``, a single collected exception is re-raised as is instead
        of being wrapped in an exception group, by default False.
    level_success : LogLevel
        Level for success messages, :attr:`~fastretry.logging.LogLevel.OFF` by default.
    level_retry : LogLevel
        Level for retry messages,
        :attr:`~fastretry.logging.LogLevel.WARNING` by default.
    level_failure : LogLevel
        Level for failure messages,
        :attr:`~fastretry.logging.LogLevel.ERROR` by default.
    level_sleep : LogLevel
        Level for sleep messages, :attr:`~fastretry.logging.LogLevel.OFF` by default.
    traceback_min_level : LogLevel
        Minimum level at which a traceback is attached to the log record,
        :attr:`~fastretry.logging.LogLevel.ERROR` by default.
    install_default_handler : bool
        Whether to install the built-in console handler on the ``"fastretry"``
        logger, by default True.

    """

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
    async_callback_mode: AsyncCallbackMode = "thread_per_call"
    unwrap_single_exception: bool = False

    # --- logging ---
    level_success: LogLevel = LogLevel.OFF
    level_retry: LogLevel = LogLevel.WARNING
    level_failure: LogLevel = LogLevel.ERROR
    level_sleep: LogLevel = LogLevel.OFF

    traceback_min_level: LogLevel = LogLevel.ERROR
    install_default_handler: bool = True

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


global_defaults: Final[Defaults] = Defaults()
"""Process-wide defaults, set by ``config.retry`` and ``config.logging``."""

context_defaults: contextvars.ContextVar[Defaults | None] = contextvars.ContextVar(
    "retry_defaults",
    default=None,
)
"""Per-context defaults set by ``config.context``; ``None`` outside of the block."""


def get_defaults() -> Defaults:
    """
    Return the effective defaults for the current context.

    Returns
    -------
    Defaults
        Effective defaults for the current context.

    """
    current_defaults = context_defaults.get()
    return current_defaults if current_defaults is not None else global_defaults
