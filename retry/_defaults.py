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
import logging
import sys
import time
from typing import (
    TYPE_CHECKING,
    Final,
    Unpack,
    final,
)

from retry._types import (
    DefaultsKwargs,
    Delay,
    GlobalKwargs,
    JitterStrategy,
    LocalKwargs,
    LoggerType,
    LoggingKwargs,
    UnsetType,
)

if TYPE_CHECKING:
    from collections.abc import (
        Awaitable,
        Callable,
        Generator,
    )


def _make_default_logger() -> logging.Logger:
    """
    Create the default logger writing to stdout.

    Returns
    -------
    logging.Logger
        default logger

    """
    logger = logging.getLogger("retry")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


_DEFAULT_LOGGER: Final[logging.Logger] = _make_default_logger()


@dc.dataclass(slots=True)
class _Defaults:
    # --- retry options (per-decorator, with global defaults) ---
    attempts: int = 1
    delay: Delay = 0
    disable_logging: bool = False
    disable_warnings: bool = False

    # --- global options (application-wide) ---
    jitter_for_exponential: JitterStrategy = "none"
    jitter_for_fixed: JitterStrategy = "none"

    sync_sleep_call: Callable[[float], None] = time.sleep
    async_sleep_call: Callable[[float], Awaitable[None]] = asyncio.sleep

    # --- logging ---
    logger_sleep: LoggerType | None = None
    logger_success: LoggerType | None = None
    logger_retry: LoggerType | None = _DEFAULT_LOGGER.warning
    logger_failure: LoggerType | None = _DEFAULT_LOGGER.error

    include_traceback_in_retry_log: bool = False
    include_traceback_in_failure_log: bool = True

    logger_traceback_kwarg: str = "exc_info"

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
    Configure loggers used by the retry decorators.

    By default, all loggers are built-in ``logging.Logger`` methods
    writing to stdout.

    Pass ``None`` to disable a specific logger.

    Parameters
    ----------
    logger_success : LoggerType | None, optional
        Callable for messages emitted after a successful attempt.
    logger_retry : LoggerType | None, optional
        Callable for messages emitted after a failed attempt, before sleeping.
    logger_failure : LoggerType | None, optional
        Callable for messages emitted after all attempts have failed.
    logger_sleep : LoggerType | None, optional
        Callable for messages emitted before sleeping between attempts.
    include_traceback_in_retry_log : bool, optional
        Include traceback in retry logs, by default False.
    include_traceback_in_failure_log : bool, optional
        Include traceback in failure logs, by default True.
    logger_traceback_kwarg : str, optional
        Name of the keyword argument used to pass the exception to the
        logger, by default "exc_info".

    """
    defaults.set(**kwargs)


def set_retry_defaults(**kwargs: Unpack[LocalKwargs]) -> None:
    """
    Override default retry options.

    These options can also be passed per-decorator via ``@retry(...)``.
    Each parameter, if provided, replaces the corresponding factory
    default for all subsequently created retry decorators.

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
        Default jitter strategy for exponential delay, by default "full"
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
