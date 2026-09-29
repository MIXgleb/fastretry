"""
Abstract base class for retry decorators.

``BaseRetrying`` holds the shared state (attempts, delay, logging flags)
and the shared blocks (``exception_block``, ``failed_block``,
``copy``). Concrete sync and async implementations live in
:mod:`~.sync_retry` and :mod:`~.async_retry`.
"""

import copy
import time
from abc import (
    ABC,
    abstractmethod,
)
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Any,
    Final,
    Self,
    final,
)

from retry._defaults import (
    defaults,
)
from retry._utils import (
    UNSET,
    AttemptState,
    CallOptions,
    DecoratorOptions,
    Delay,
    DelayCalculator,
    ExponentialDelay,
    FunctionTypes,
    GlobalOptions,
    JitterStrategy,
    Log,
    LoggerConfig,
    ResolvedRetryCallbacks,
    RetryCallbacks,
    RetryStats,
    UnsetType,
    Warnings,
    noop_callback,
)


class BaseRetrying[R, WrappedFunc: Callable[..., Any]](ABC):
    """Retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = (
        "_callbacks",
        "_log",
        "_stats",
        "_warnings",
        "attempts",
        "delay",
        "disable_logging",
        "disable_warnings",
        "include_traceback_in_failure_log",
        "include_traceback_in_retry_log",
        "jitter",
        "logger_failure",
        "logger_retry",
        "logger_sleep",
        "logger_success",
        "logger_traceback_kwarg",
        "re_raise_exception",
        "return_default_value",
    )

    def __init__(  # ruff: ignore[too-many-arguments]
        self,
        *,
        attempts: int | UnsetType = UNSET,
        return_default_value: R | UnsetType = UNSET,
        delay: Delay | UnsetType = UNSET,
        jitter: JitterStrategy | UnsetType = UNSET,
        disable_logging: bool | UnsetType = UNSET,
        disable_warnings: bool | UnsetType = UNSET,
        callbacks: RetryCallbacks | UnsetType = UNSET,
    ) -> None:
        """
        Initialize the retry decorator.

        Parameters
        ----------
        attempts : int, optional
            Number of attempts
        return_default_value : Any, optional
            Default value returned if the function fails after all attempts,
        delay : Delay, optional
            Delay between attempts in seconds. May be a plain ``float`` for a
            fixed delay or an :class:`~._utils._delay.ExponentialDelay` for
            exponential backoff.
        jitter : JitterStrategy, optional
            Jitter strategy overriding the default for the given delay type.
            When omitted, ``jitter_for_exponential`` or ``jitter_for_fixed``
            from the global defaults is used.
        disable_logging : bool, optional
            Disable all logging
        disable_warnings : bool, optional
            Disable all warnings
        callbacks : RetryCallbacks, optional
            Callbacks invoked during retry processing. When omitted, defaults
            from :mod:`~._utils._callbacks` are used. Individual callbacks may
            be set to ``None`` to disable them.

        """
        # --- per-decorator options ---
        self.attempts: Final = self._resolve(
            passed=attempts,
            default=defaults.attempts,
        )
        self.return_default_value: Final = self._resolve(
            passed=return_default_value,
            default=UNSET,
        )
        self.delay: Final = self._resolve(
            passed=delay,
            default=defaults.delay,
        )
        self.disable_logging: Final = self._resolve(
            passed=disable_logging,
            default=defaults.disable_logging,
        )
        self.disable_warnings: Final = self._resolve(
            passed=disable_warnings,
            default=defaults.disable_warnings,
        )
        self._callbacks: Final = self._resolve_callbacks(
            callbacks=callbacks,
        )

        # --- logger configuration ---
        self.logger_success: Final = defaults.logger_success
        self.logger_retry: Final = defaults.logger_retry
        self.logger_failure: Final = defaults.logger_failure
        self.logger_sleep: Final = defaults.logger_sleep
        self.logger_traceback_kwarg: Final = defaults.logger_traceback_kwarg
        self.include_traceback_in_retry_log: Final = defaults.include_traceback_in_retry_log
        self.include_traceback_in_failure_log: Final = defaults.include_traceback_in_failure_log

        # --- internal helpers ---
        self._log = Log(self.logger_config)
        self._warnings = Warnings(disable_warnings=self.disable_warnings)

        # --- derived options ---
        self.jitter: Final = self._derive_jitter(jitter=jitter)
        self.re_raise_exception: Final = isinstance(self.return_default_value, UnsetType)
        self._stats: Final = RetryStats(
            log=self._log,
            decorator=DecoratorOptions(
                attempts=self.attempts,
                return_default_value=self.return_default_value,
                delay=self.delay,
                jitter=self.jitter,
                disable_logging=self.disable_logging,
                disable_warnings=self.disable_warnings,
                re_raise_exception=self.re_raise_exception,
            ),
            global_options=GlobalOptions(
                jitter_for_exponential=defaults.jitter_for_exponential,
                jitter_for_fixed=defaults.jitter_for_fixed,
                sync_sleep_call=defaults.sync_sleep_call,
                async_sleep_call=defaults.async_sleep_call,
                include_traceback_in_retry_log=self.include_traceback_in_retry_log,
                include_traceback_in_failure_log=self.include_traceback_in_failure_log,
                logger_traceback_kwarg=self.logger_traceback_kwarg,
            ),
            call=CallOptions(),
            attempt=AttemptState(),
        )

    @final
    @property
    def logger_config(self) -> LoggerConfig:
        """
        Immutable snapshot of the logging configuration.

        Built on demand from the current logging-related attributes. Passed
        to :class:`~._utils._logs.Log` so that the logger cannot mutate the
        retry configuration.

        Returns
        -------
        LoggerConfig
            Snapshot of the logging configuration.

        """
        return LoggerConfig(
            logger_retry=self.logger_retry,
            logger_failure=self.logger_failure,
            logger_sleep=self.logger_sleep,
            logger_success=self.logger_success,
            logger_traceback_kwarg=self.logger_traceback_kwarg,
            include_traceback_in_retry_log=self.include_traceback_in_retry_log,
            include_traceback_in_failure_log=self.include_traceback_in_failure_log,
            disable_logging=self.disable_logging,
            disable_warnings=self.disable_warnings,
        )

    @final
    def copy(self) -> Self:
        """
        Copy this object.

        Returns
        -------
        Self
            copied instance of the class

        """
        return copy.copy(self)

    @final
    def wraps(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Wrap a function with retry logic.

        Performs shared pre-checks and delegates the actual wrapping to
        :meth:`_wrap`. Only ``Exception`` subclasses are retried; all
        ``BaseException`` subclasses (such as ``KeyboardInterrupt``,
        ``SystemExit``, and ``asycnio.CancelError``) propagate immediately.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to wrap

        Returns
        -------
        Callable[..., Any]
            Wrapped function with the same signature

        """
        if not isinstance(self.return_default_value, UnsetType):
            FunctionTypes(func).warn_on_return_default_mismatch(
                return_default_value=self.return_default_value,
                disable_warnings=self.disable_warnings,
            )

        return self._wrap(func)

    @abstractmethod
    def _wrap(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Implement the wrapping logic for a concrete retry strategy.

        Called by :meth:`wraps` after shared pre-checks.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to wrap

        Returns
        -------
        Callable[..., Any]
            Wrapped function with the same signature

        """
        raise NotImplementedError

    @abstractmethod
    def _sleep(
        self,
        *,
        stats_attempt: AttemptState,
    ) -> Awaitable[None] | None:
        """
        Sleep between attempts.

        Does nothing on the last attempt. Computes the delay via
        ``delay_calculator``.

        Parameters
        ----------
        stats_attempt : AttemptState
            Per-attempt state.

        """
        raise NotImplementedError

    @abstractmethod
    def _call_callback(
        self,
        *,
        callback: Callable[[RetryStats], Awaitable[None] | None],
        stats: RetryStats,
    ) -> Awaitable[None] | None:
        """
        Invoke a retry callback.

        Subclasses decide how to handle an awaitable result:

        - :class:`AsyncRetrying` always awaits it.
        - :class:`SyncRetrying` runs it synchronously. When no event loop is
        running, :func:`asyncio.run` is used; when a loop is already
        running, the coroutine is executed in a separate thread with its
        own loop. The latter is expensive and blocks the caller until the
        callback completes.

        Parameters
        ----------
        callback : Callable[[RetryStats], Awaitable[None] | None]
            Callback to invoke.
        stats : RetryStats
            Current retry statistics.

        Returns
        -------
        Awaitable[None] | None
            Awaitable when the callback is async, ``None`` otherwise.

        """
        raise NotImplementedError

    def _prepare_success(  # ruff: ignore[no-self-use]
        self,
        *,
        stats_attempt: AttemptState,
        result: object,
    ) -> None:
        """
        Record a successful attempt in ``stats``.

        Parameters
        ----------
        stats_attempt : AttemptState
            Per-attempt state.
        result : object
            Result returned by the wrapped function.

        """
        stats_attempt.result = result
        stats_attempt.elapsed = time.monotonic() - stats_attempt.started_at

    def _prepare_retry(
        self,
        *,
        stats_attempt: AttemptState,
        exc: Exception,
        delay_calculator: DelayCalculator,
    ) -> None:
        """
        Record a failed attempt in ``stats``.

        Parameters
        ----------
        stats_attempt : AttemptState
            Per-attempt state.
        exc : Exception
            Exception raised by the wrapped function.
        delay_calculator : DelayCalculator
            Calculator used to compute the delay before the next attempt.

        """
        stats_attempt.last_exception = exc
        stats_attempt.exceptions.append(exc)
        stats_attempt.elapsed = time.monotonic() - stats_attempt.started_at
        stats_attempt.computed_delay = UNSET

        if stats_attempt.retry_index < self.attempts:
            stats_attempt.computed_delay = delay_calculator.compute(stats_attempt.retry_index)

    def _prepare_failure(
        self,
        *,
        stats_attempt: AttemptState,
    ) -> None:
        """
        Record the final failure in ``stats``.

        Parameters
        ----------
        stats_attempt : AttemptState
            Per-attempt state.

        """
        stats_attempt.elapsed = time.monotonic() - stats_attempt.started_at

        if not self.re_raise_exception or stats_attempt.last_exception is None:
            stats_attempt.result = self.return_default_value

    def _raise_if_needed(
        self,
        *,
        stats_attempt: AttemptState,
    ) -> None:
        """
        Raise a single :exc:`ExceptionGroup` if re-raising is enabled.

        Does nothing when ``re_raise_exception`` is ``False`` or there are
        no caught exceptions. Otherwise, raises an :exc:`ExceptionGroup`
        containing every exception from the failed attempts, in order.

        Parameters
        ----------
        stats_attempt : AttemptState
            Per-attempt state.

        Raises
        ------
        ExceptionGroup
            Containing all exceptions from ``stats.attempt.exceptions``.

        """
        if self.re_raise_exception and stats_attempt.exceptions:
            msg = f"All {stats_attempt.retry_index} attempts failed"
            raise ExceptionGroup(msg, stats_attempt.exceptions)

    def _derive_jitter(
        self,
        *,
        jitter: JitterStrategy | UnsetType,
    ) -> JitterStrategy:
        """
        Resolve the jitter strategy after initialization.

        If ``jitter`` is not provided, the strategy is chosen based on the
        delay type: ``defaults.jitter_for_exponential`` for
        :class:`~._utils._delay.ExponentialDelay`, or
        ``defaults.jitter_for_fixed`` for a plain ``float`` delay.

        Parameters
        ----------
        jitter : JitterStrategy | UnsetType
            Explicit jitter strategy, or ``UNSET`` to fall back to the
            default for the configured delay type.

        Returns
        -------
        JitterStrategy
            Resolved jitter strategy.

        """
        if not isinstance(jitter, UnsetType):
            return jitter

        if isinstance(self.delay, ExponentialDelay):
            return defaults.jitter_for_exponential
        return defaults.jitter_for_fixed

    @staticmethod
    def _resolve_callbacks(
        *,
        callbacks: RetryCallbacks | UnsetType,
    ) -> ResolvedRetryCallbacks:
        """
        Resolve the callbacks for a decorator.

        Resolution order for each callback: per-decorator value, then global
        default (from ``defaults.on_retry`` / ``on_success`` / ``on_failure``).
        ``None`` values disable the callback by substituting a no-op.

        Parameters
        ----------
        callbacks : RetryCallbacks | UnsetType
            Per-decorator callback overrides, or ``UNSET`` to use only the
            global defaults.

        Returns
        -------
        ResolvedRetryCallbacks
            Fully resolved callbacks with all three fields populated.

        """
        if isinstance(callbacks, UnsetType):
            return ResolvedRetryCallbacks(
                on_success=defaults.on_success or noop_callback,
                on_retry=defaults.on_retry or noop_callback,
                on_failure=defaults.on_failure or noop_callback,
            )
        return ResolvedRetryCallbacks(
            on_success=callbacks.get("on_success", defaults.on_success) or noop_callback,
            on_retry=callbacks.get("on_retry", defaults.on_retry) or noop_callback,
            on_failure=callbacks.get("on_failure", defaults.on_failure) or noop_callback,
        )

    @staticmethod
    def _resolve[T](
        *,
        passed: T | UnsetType,
        default: T,
    ) -> T:
        """
        Resolve a value by priority: passed > factory default.

        Parameters
        ----------
        passed : T | UnsetType
            passed value
        default: T
            factory default value

        Returns
        -------
        T
            set value

        """
        return passed if not isinstance(passed, UnsetType) else default
