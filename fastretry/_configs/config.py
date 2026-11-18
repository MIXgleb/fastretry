"""Configuration entry point for retry defaults and logging."""

import contextlib
import dataclasses as dc
from collections.abc import (
    Generator,
)
from typing import (
    Unpack,
)

from fastretry._compat.types import (
    DefaultsKwargs,
    LoggingDefaultsKwargs,
    RetryDefaultsKwargs,
)
from fastretry._configs.defaults import (
    context_defaults,
    get_defaults,
    global_defaults,
)


class _ResetNamespace:
    """Namespace for resetting defaults."""

    __slots__ = ()

    def __call__(self) -> None:
        """Reset all defaults to their factory values."""
        get_defaults().reset()


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
        attempts : int, ``optional``
            Default number of attempts, by default 1. A value below 1 is
            replaced with 1 and reported with a :exc:`UserWarning` when a
            decorator using these defaults is created.
        delay : Delay, ``optional``
            Default delay between attempts, in seconds, by default 0. A
            negative fixed delay is replaced with 0 and reported with a
            :exc:`UserWarning` when a decorator using these defaults is
            created; invalid :class:`~fastretry.delays.ExponentialDelay`
            parameters raise :exc:`ValueError` at that point. A
            :data:`~fastretry.delays.WaitCallable` computes the delay for each
            attempt.
        disable_logging : bool, ``optional``
            Disable all logging by default, by default False.
        disable_warnings : bool, ``optional``
            Disable all warnings by default, by default False.
        retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
            Exception types that trigger a retry. Defaults to ``Exception``.
        no_retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
            Exception types that are never retried, even if they match
            ``retry_on``. Takes precedence. Defaults to ``()``.
        unwrap_single_exception : bool, ``optional``
            Re-raise the single collected exception as is instead of
            wrapping it in an exception group. When two or more exceptions
            were collected, an exception group is still raised. Useful when
            migrating from libraries that re-raise the original exception,
            by default False.
        on_success : CallbackType | None, ``optional``
            Default callback invoked after a successful attempt,
            by default :func:`~fastretry.callbacks.default_on_success`.
        on_retry : CallbackType | None, ``optional``
            Default callback invoked after a failed attempt,
            by default :func:`~fastretry.callbacks.default_on_retry`.
        on_failure : CallbackType | None, ``optional``
            Default callback invoked after all attempts have failed,
            by default :func:`~fastretry.callbacks.default_on_failure`.
        jitter_for_exponential : JitterStrategy, ``optional``
            Default jitter strategy for exponential delay,
            by default ``"none"``.
        jitter_for_fixed : JitterStrategy, ``optional``
            Default jitter strategy for fixed delay,
            by default ``"none"``.
        async_callback_mode : AsyncCallbackMode, ``optional``
            How async callbacks of synchronous functions are dispatched.

            - ``"thread_per_call"`` (default) starts a thread with its own
              event loop for every callback invocation when an event loop is
              already running (about 3 ms per callback). This is the safest
              and most isolated mode.
            - ``"shared_loop_when_running"`` submits the callback to a process-wide
              shared loop in that case (about 0.1 ms), and keeps
              :func:`asyncio.run` when no loop is running.
            - ``"shared_loop_always"`` submits the callback to the shared loop in
              every case.

        """
        get_defaults().set(**kwargs)


class _LoggingNamespace:
    """Namespace for logging configuration."""

    __slots__ = ()

    def __call__(
        self,
        **kwargs: Unpack[LoggingDefaultsKwargs],
    ) -> None:
        """
        Configure logging for the retry decorators.

        Logging is handled by the standard :mod:`logging` module
        through a single logger named ``"retry"``.

        By default, a console handler writing to :data:`sys.stderr` is
        installed on the first log record, so messages are visible in the
        console without any setup. The handler is used only when neither
        the ``"retry"`` logger nor any of its ancestors has handlers, and
        the decision is taken once per process. Once the application
        configures :mod:`logging` (:func:`logging.basicConfig`,
        :func:`logging.config.dictConfig`, or a handler attached to the
        ``"retry"`` logger), the built-in handler is not installed and the
        application configuration is used as is.

        To keep the package silent until :mod:`logging` is configured,
        pass ``install_default_handler=False``.

        Each log kind has its own level. Set a level to
        :attr:`~fastretry.logging.LogLevel.OFF` to disable that kind.

        Parameters
        ----------
        level_success : LogLevel, ``optional``
            Level for messages emitted after a successful attempt,
            by default :attr:`~fastretry.logging.LogLevel.OFF`.
        level_retry : LogLevel, ``optional``
            Level for messages emitted after a failed attempt,
            by default :attr:`~fastretry.logging.LogLevel.WARNING`.
        level_failure : LogLevel, ``optional``
            Level for messages emitted after all attempts have failed,
            by default :attr:`~fastretry.logging.LogLevel.ERROR`.
        level_sleep : LogLevel, ``optional``
            Level for messages emitted before sleeping between attempts,
            by default :attr:`~fastretry.logging.LogLevel.OFF`.
        traceback_min_level : LogLevel, ``optional``
            Minimum level at which a traceback is attached to the log
            record, by default :attr:`~fastretry.logging.LogLevel.ERROR`.
        install_default_handler : bool, ``optional``
            Whether to install the built-in console handler on the
            ``"retry"`` logger. When ``True``, a handler writing to
            :data:`sys.stderr` is attached on the first log record, unless
            :mod:`logging` is already configured. When ``False``, a
            :class:`logging.NullHandler` is attached instead, so the package
            emits nothing until :mod:`logging` is configured by the
            application. By default True.

        """
        get_defaults().set(**kwargs)


class _ContextNamespace:
    """Namespace for per-context retry defaults."""

    __slots__ = ()

    @contextlib.contextmanager
    def __call__(
        self,
        **kwargs: Unpack[DefaultsKwargs],
    ) -> Generator[None]:
        """
        Use a per-context defaults instance within the block.

        Creates a fresh copy of the global defaults, applies ``kwargs``
        on top, and installs it for the duration of the block. Inside
        the block:

        - :attr:`~config.retry` and :attr:`~config.logging` mutate the
          per-context instance instead of the global one;
        - decorators created inside the block read defaults from the
          per-context instance.

        Changes are isolated to the current :class:`contextvars.Context`:
        in asyncio, each task sees its own instance; in threaded code,
        each thread sees its own. Outside the block, the global defaults
        are used again.

        Parameters
        ----------
        **kwargs : Unpack[DefaultsKwargs]
            Initial overrides applied on top of the copied defaults.

        """
        fresh = dc.replace(global_defaults)
        fresh.set(**kwargs)

        token = context_defaults.set(fresh)

        try:
            yield
        finally:
            context_defaults.reset(token)


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
    context : _ContextNamespace
        Callable namespace for per-context default overrides.

    """

    __slots__ = ()

    retry = _RetryNamespace()
    logging = _LoggingNamespace()
    reset = _ResetNamespace()
    context = _ContextNamespace()


config = _ConfigNamespace()
"""Global configuration entry point: ``config.retry``, ``config.logging``, ``config.context``."""
