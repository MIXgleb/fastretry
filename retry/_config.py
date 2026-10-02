"""Configuration entry point for retry defaults and logging."""

import contextlib
import dataclasses as dc
from collections.abc import (
    Generator,
)
from typing import (
    Unpack,
)

from retry._defaults import (
    defaults,
)
from retry._types import (
    DefaultsKwargs,
    LoggingKwargs,
    RetryDefaultsKwargs,
)


class _ResetNamespace:
    """Namespace for resetting defaults."""

    __slots__ = ()

    def __call__(self) -> None:
        """
        Reset all defaults to their factory values.

        Restores every option configured via :attr:`config.retry` and
        :attr:`config.logging` to the value it had at import time.
        Useful in tests to avoid leaking configuration between test
        cases.
        """
        defaults.reset()


class _RetryNamespace:
    """Namespace for default retry options."""

    __slots__ = ()

    def __call__(
        self,
        **kwargs: Unpack[RetryDefaultsKwargs],
    ) -> None:
        """
        Configure default retry options.

        These options apply to all subsequently created retry
        decorators. Per-decorator options passed to ``@retry(...)``
        take precedence over these defaults.

        Parameters
        ----------
        attempts : int, optional
            Default number of attempts, by default 1.
        delay : Delay, optional
            Default delay between attempts, in seconds, by default 0.
        disable_logging : bool, optional
            Disable all logging by default, by default False.
        disable_warnings : bool, optional
            Disable all warnings by default, by default False.
        on_success : Callable[[RetryStats], None] | None, optional
            Default callback invoked after a successful attempt,
            by default :func:`default_on_success`.
        on_retry : Callable[[RetryStats], None] | None, optional
            Default callback invoked after a failed attempt,
            by default :func:`default_on_retry`.
        on_failure : Callable[[RetryStats], None] | None, optional
            Default callback invoked after all attempts have failed,
            by default :func:`default_on_failure`.
        jitter_for_exponential : JitterStrategy, optional
            Default jitter strategy for exponential delay,
            by default ``"none"``.
        jitter_for_fixed : JitterStrategy, optional
            Default jitter strategy for fixed delay,
            by default ``"none"``.
        sync_sleep_call : Callable[[float], None], optional
            Default sync sleep callable, by default :func:`time.sleep`.
        async_sleep_call : Callable[[float], Awaitable[None]], optional
            Default async sleep callable, by default :func:`asyncio.sleep`.

        """
        defaults.set(**kwargs)


class _LoggingNamespace:
    """Namespace for logging configuration."""

    __slots__ = ()

    def __call__(
        self,
        **kwargs: Unpack[LoggingKwargs],
    ) -> None:
        """
        Configure logging for the retry decorators.

        Logging is handled by the standard :mod:`logging` module
        through a single logger named ``"retry"``, which writes to
        stdout by default.

        Each log kind has its own level. Set a level to
        :attr:`LogLevel.OFF` to disable that kind.

        Parameters
        ----------
        level_success : LogLevel, optional
            Level for messages emitted after a successful attempt,
            by default :attr:`LogLevel.OFF`.
        level_retry : LogLevel, optional
            Level for messages emitted after a failed attempt,
            by default :attr:`LogLevel.WARNING`.
        level_failure : LogLevel, optional
            Level for messages emitted after all attempts have failed,
            by default :attr:`LogLevel.ERROR`.
        level_sleep : LogLevel, optional
            Level for messages emitted before sleeping between attempts,
            by default :attr:`LogLevel.OFF`.
        traceback_min_level : LogLevel, optional
            Minimum level at which a traceback is attached to the log
            record, by default :attr:`LogLevel.ERROR`.

        """
        defaults.set(**kwargs)


class _TemporaryNamespace:
    """Namespace for temporary default overrides."""

    __slots__ = ()

    @contextlib.contextmanager
    def __call__(
        self,
        **kwargs: Unpack[DefaultsKwargs],
    ) -> Generator[None]:
        """
        Temporarily override defaults, restoring them on exit.

        Useful in tests: the previous values are restored even if the
        body raises.

        Parameters
        ----------
        **kwargs : Unpack[DefaultsKwargs]
            Defaults to override for the duration of the block.

        """
        snapshot = {f.name: getattr(defaults, f.name) for f in dc.fields(defaults)}
        defaults.set(**kwargs)

        try:
            yield
        finally:
            for name, value in snapshot.items():
                setattr(defaults, name, value)


class _ConfigNamespace:
    """
    Top-level configuration namespace.

    Attributes
    ----------
    retry : _RetryNamespace
        Callable namespace for default retry options.
    logging : _LoggingNamespace
        Callable namespace for logging configuration.
    reset : _ResetNamespace
        Callable namespace for resetting all defaults.
    temporary : _TemporaryNamespace
        Callable namespace for temporary default overrides.

    """

    __slots__ = ()

    retry = _RetryNamespace()
    logging = _LoggingNamespace()
    reset = _ResetNamespace()
    temporary = _TemporaryNamespace()


config = _ConfigNamespace()
