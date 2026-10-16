"""Retry statistics passed to callbacks."""

import dataclasses as dc
import traceback
from collections.abc import (
    Awaitable,
    Callable,
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
from fastretry._utils.delay import (
    Delay,
    JitterStrategy,
)
from fastretry._utils.logs import (
    Log,
    LogLevel,
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
        Delay configuration (fixed or exponential).
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
        Only relevant for :class:`~fastretry.async_retry.AsyncRetrying`.

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
    sync_sleep_call : Callable[[float], None]
        Sync callable used to sleep between attempts.
    async_sleep_call : Callable[[float], Awaitable[None]]
        Async callable used to sleep between attempts.
    traceback_min_level : LogLevel
        Minimum level at which a traceback is attached to the log record.
        Messages below this level are logged without traceback.

    """

    jitter_for_exponential: JitterStrategy
    jitter_for_fixed: JitterStrategy

    sync_sleep_call: Callable[[float], None]
    async_sleep_call: Callable[[float], Awaitable[None]]

    traceback_min_level: LogLevel


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
    elapsed : float
        Seconds elapsed since ``started_at``.
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
    elapsed: float = 0.0
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
            "elapsed": attempt.elapsed,
            "previous_delay": attempt.previous_delay,
            "computed_delay": attempt.computed_delay,
            "exception_type": (
                type(attempt.last_exception).__name__
                if attempt.last_exception is not None
                else None
            ),
            "retry_aborted": attempt.retry_aborted,
        }

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
