"""Retry statistics passed to callbacks."""

import dataclasses as dc
import traceback
from collections.abc import (
    Mapping,
)
from concurrent.futures import (
    Executor,
)
from typing import (
    Any,
)

from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._utils.delays import (
    Delay,
    JitterStrategy,
)
from fastretry._utils.logs import (
    Log,
    LogLevel,
)
from fastretry._utils.shared_loop import (
    AsyncCallbackMode,
)


@dc.dataclass(frozen=True, slots=True)
class DecoratorOptions:
    """
    Options fixed at decorator construction.

    Attributes
    ----------
    attempts : int
        Total number of attempts.
    return_default_value : Any
        Value returned on failure, or ``UNSET`` if the wrapper re-raises.
    delay : Delay
        Delay configuration: fixed seconds, exponential or custom.
    jitter : JitterStrategy
        Jitter strategy applied to the computed delay.
    disable_logging : bool
        If ``True``, all logging is skipped.
    disable_warnings : bool
        If ``True``, warnings are suppressed.
    re_raise_exception : bool
        If ``True``, the last exception is re-raised after all attempts.
    retry_on : type[BaseException] | tuple[type[BaseException], ...]
        Exception types that trigger a retry.
    no_retry_on : type[BaseException] | tuple[type[BaseException], ...]
        Exception types that are never retried, even if they match
        ``retry_on``. Takes precedence.
    executor : Executor | None
        Executor used to run sync functions in an async context.
        Only relevant for :class:`~fastretry._retryings.async_retrying.AsyncRetrying`.

    """

    attempts: int
    return_default_value: Any
    delay: Delay
    jitter: JitterStrategy
    disable_logging: bool
    disable_warnings: bool
    re_raise_exception: bool
    retry_on: type[BaseException] | tuple[type[BaseException], ...]
    no_retry_on: type[BaseException] | tuple[type[BaseException], ...]
    executor: Executor | None


@dc.dataclass(frozen=True, slots=True)
class GlobalOptions:
    """
    Application-wide options resolved from global defaults.

    Attributes
    ----------
    jitter_for_exponential : JitterStrategy
        Default jitter strategy for exponential delay.
    jitter_for_fixed : JitterStrategy
        Default jitter strategy for fixed delay.
    traceback_min_level : LogLevel
        Minimum level at which a traceback is attached to the log record.
        Messages below this level are logged without traceback.
    install_default_handler : bool
        Whether to install the built-in console handler on the
        ``"fastretry"`` logger.
    async_callback_mode : AsyncCallbackMode
        How async callbacks of synchronous functions are dispatched.
    unwrap_single_exception : bool
        If ``True``, a failure with exactly one collected exception
        re-raises that exception as is instead of wrapping it in an
        exception group.

    """

    jitter_for_exponential: JitterStrategy
    jitter_for_fixed: JitterStrategy

    traceback_min_level: LogLevel
    install_default_handler: bool

    async_callback_mode: AsyncCallbackMode
    unwrap_single_exception: bool


@dc.dataclass(frozen=True, slots=True, repr=False)
class CallOptions:
    """
    Arguments of the wrapped call.

    Attributes
    ----------
    args : tuple[Any, ...]
        Positional arguments of the call.
    kwargs : Mapping[str, Any]
        Keyword arguments of the call.

    """

    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = dc.field(default_factory=dict[str, Any])


@dc.dataclass(slots=True)
class AttemptState:
    """
    Per-attempt state, updated by the wrapper as attempts progress.

    Attributes
    ----------
    fname : str
        Qualified name of the wrapped function, or ``"<anonymous>"``.
    retry_index : int
        1-based index of the current attempt.
    started_at : float
        Monotonic timestamp captured at the start of the call.
    total_elapsed : float
        Seconds elapsed since ``started_at``: every finished attempt plus
        every delay between them.
    attempt_started_at : float
        Monotonic timestamp captured at the start of the current attempt.
    attempt_duration : float
        Seconds the current (the most recently finished) attempt took,
        excluding callbacks and delays. ``0.0`` until an attempt finishes.
    attempt_durations : list[float]
        Durations of all finished attempts, in order. The last item equals
        :attr:`attempt_duration`.
    previous_delay : float | None
        Delay used on the previous attempt, or ``None`` on the first retry.
        Used by the ``"decorrelated"`` jitter strategy.
    computed_delay : float | UnsetType
        Delay computed for the upcoming attempt, or ``UNSET`` if not yet
        computed.
    result : object | UnsetType
        Result of the successful call, or ``UNSET`` if the call has not
        succeeded.
    last_exception : BaseException | None
        Exception from the most recent attempt, or ``None`` if no attempt
        has failed yet.
    exceptions : list[BaseException]
        All exceptions raised across attempts, in order. Empty until the
        first failure.
    retry_aborted : bool
        ``True`` when the retry loop was aborted before exhausting all
        attempts, because the caught exception did not match ``retry_on``
        or matched ``no_retry_on``.

    """

    fname: str = ""
    retry_index: int = 0
    started_at: float = 0.0
    total_elapsed: float = 0.0
    attempt_started_at: float = 0.0
    attempt_duration: float = 0.0
    attempt_durations: list[float] = dc.field(default_factory=list[float])
    previous_delay: float | None = None
    computed_delay: float | UnsetType = UNSET
    result: object | UnsetType = UNSET
    last_exception: BaseException | None = dc.field(default=None, repr=False)
    exceptions: list[BaseException] = dc.field(default_factory=list[BaseException], repr=False)
    retry_aborted: bool = False

    @property
    def exceptions_with_traceback(self) -> tuple[str, ...]:
        """
        Formatted tracebacks of all caught exceptions.

        Returns
        -------
        tuple[str, ...]
            One formatted traceback per caught exception, in order.

        """
        return tuple(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            for exc in self.exceptions
        )

    def format_exception(
        self,
        exc: BaseException | UnsetType | None = UNSET,
    ) -> str:
        """
        Format a traceback for an exception.

        Parameters
        ----------
        exc : BaseException | UnsetType | None, ``optional``
            Exception to format. When omitted (``UNSET``), the value of
            :attr:`last_exception` is used.

        Returns
        -------
        str
            Formatted traceback, or ``"<no exception>"`` when the chosen
            exception is ``None``.

        """
        if isinstance(exc, UnsetType):
            exc = self.last_exception

        if exc is None:
            return "<no exception>"

        return "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__),
        )


@dc.dataclass(slots=True)
class RetryStats:
    """
    State passed to retry callbacks.

    A template instance is created once per decorator; the
    wrapper derives a fresh copy per call via :meth:`for_call`
    and mutates it as attempts progress.

    The wrapper owns the per-call instance, so treat every
    :class:`RetryStats` received by a callback or returned by
    introspection as read-only: its fields describe the live run, and
    writing to them corrupts retry bookkeeping. Call :meth:`snapshot`
    before passing the state to another thread, task or storage that
    outlives the call.

    Attributes
    ----------
    log : Log
        Logger bound to the retry configuration.
    decorator : DecoratorOptions
        Options fixed at decorator construction.
    global_options : GlobalOptions
        Application-wide options.
    call : CallOptions
        Arguments of the wrapped call.
    attempt : AttemptState
        Per-attempt state.

    """

    log: Log
    decorator: DecoratorOptions
    global_options: GlobalOptions
    call: CallOptions
    attempt: AttemptState

    @property
    def log_extra(self) -> Mapping[str, object]:
        """
        Structured fields for the ``logging`` ``extra`` argument.

        Suitable for passing to log via ``extra``.
        Useful for structured logging backends
        (Sentry, Datadog) that index ``LogRecord`` attributes.

        Returns
        -------
        Mapping[str, object]
            Fields describing the current call and attempt.

        """
        attempt = self.attempt
        return {
            "fname": attempt.fname,
            "retry_index": attempt.retry_index,
            "attempts": self.decorator.attempts,
            "started_at": attempt.started_at,
            "total_elapsed": attempt.total_elapsed,
            "attempt_started_at": attempt.attempt_started_at,
            "attempt_duration": attempt.attempt_duration,
            "previous_delay": attempt.previous_delay,
            "computed_delay": attempt.computed_delay,
            "exception_type": (
                type(attempt.last_exception).__name__
                if attempt.last_exception is not None
                else None
            ),
            "retry_aborted": attempt.retry_aborted,
        }

    def snapshot(self) -> "RetryStats":
        """
        Return a detached copy of the current state.

        The retry loop keeps mutating the live instance while attempts
        progress, so a caller that reports several fields together should
        read a snapshot: afterwards its fields no longer change. The copy
        shares the immutable call context (logger, decorator options, call
        arguments) and owns its own :class:`AttemptState` with copies of
        its mutable lists. Fields are read without pausing the loop, so
        they describe the state around the moment of the call.

        Returns
        -------
        RetryStats
            Copy of the current state, detached from the retry loop.

        """
        attempt = self.attempt
        return dc.replace(
            self,
            attempt=dc.replace(
                attempt,
                attempt_durations=list(attempt.attempt_durations),
                exceptions=list(attempt.exceptions),
            ),
        )

    def for_call(
        self,
        *,
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
        fname: str,
        started_at: float,
    ) -> "RetryStats":
        """
        Return a fresh copy of this template for a single call.

        Parameters
        ----------
        args : tuple[Any, ...]
            Positional arguments of the call.
        kwargs : Mapping[str, Any]
            Keyword arguments of the call.
        fname : str
            Qualified name of the wrapped function.
        started_at : float
            Monotonic timestamp at the start of the call.

        Returns
        -------
        RetryStats
            Fresh per-call instance.

        """
        return dc.replace(
            self,
            call=CallOptions(
                args=args,
                kwargs=kwargs,
            ),
            attempt=AttemptState(
                fname=fname,
                started_at=started_at,
            ),
        )
