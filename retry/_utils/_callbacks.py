"""
Retry lifecycle callbacks.

Defines the :class:`~retry._utils._callbacks.RetryCallbacks`
mapping accepted by the retry decorators, its fully
resolved counterpart :class:`~retry._utils._callbacks.ResolvedRetryCallbacks`,
and the built-in callback implementations used when the
user does not provide their own.
"""

import dataclasses as dc
from collections.abc import (
    Callable,
)
from typing import (
    TypedDict,
)

from retry._utils._stats import (
    RetryStats,
)
from retry._utils._unset import (
    UnsetType,
)


class RetryCallbacks(TypedDict, total=False):
    """
    Callbacks invoked during retry processing.

    All callbacks are optional. When a callback is omitted, the
    corresponding built-in default is used. Set a callback explicitly
    to ``None`` to disable it.

    Attributes
    ----------
    on_success : Callable[[RetryStats], None] | None, ``optional``
        Called after a successful attempt. No default is provided.
    on_retry : Callable[[RetryStats], None] | None, ``optional``
        Called after a failed attempt, before sleeping.
    on_failure : Callable[[RetryStats], None] | None, ``optional``
        Called after all attempts have failed.

    """

    on_success: Callable[[RetryStats], None] | None
    on_retry: Callable[[RetryStats], None] | None
    on_failure: Callable[[RetryStats], None] | None


@dc.dataclass(frozen=True, slots=True)
class ResolvedRetryCallbacks:
    """
    Fully resolved retry callbacks.

    Produced by :func:`~retry.base.BaseRetrying._resolve_callbacks`
    from a user-provided :class:`~retry._utils._callbacks.RetryCallbacks` mapping.
    All keys are present and every value is a callable:
    omitted entries are filled with built-in defaults, and explicit
    ``None`` values are replaced with a no-op callback.

    Attributes
    ----------
    on_success : Callable[[RetryStats], None]
        Called after a successful attempt. Falls back to a no-op when not
        provided.
    on_retry : Callable[[RetryStats], None]
        Called after a failed attempt, before sleeping.
    on_failure : Callable[[RetryStats], None]
        Called after all attempts have failed.

    """

    on_success: Callable[[RetryStats], None]
    on_retry: Callable[[RetryStats], None]
    on_failure: Callable[[RetryStats], None]


def default_on_success(stats: RetryStats) -> None:
    """
    Default ``on_success`` callback: log the successful attempt.

    Records a ``"success"`` message via ``stats.log``, attaching
    structured fields from :attr:`~retry._utils._stats.RetryStats.log_extra`
    to the log record. The result value is included in the message when it is a
    primitive type; for complex objects only the type name is logged.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    result = stats.attempt.result

    if isinstance(result, (int, float, str, bool, bytes, type(None))):
        message = "Function executed successfully. Result: %r."
        args = (result,)
    else:
        message = "Function executed successfully. Result type: %s."
        args = (type(result).__name__,)

    _ = stats.log.record(
        log_kind="success",
        message=message,
        args=args,
        extra=stats.log_extra,
    )


def default_on_retry(stats: RetryStats) -> None:
    """
    Default ``on_retry`` callback: log the failed attempt.

    Records a ``"retry"`` message via ``stats.log``, and, when a delay
    is scheduled before the next attempt, also records a ``"sleep"``
    message. Structured fields from
    :attr:`~retry._utils._stats.RetryStats.log_extra`
    are attached to both records.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    _ = stats.log.record(
        log_kind="retry",
        message="Error executing the function. Try %d of %d.",
        args=(stats_attempt.retry_index, stats.decorator.attempts),
        last_exception=stats_attempt.last_exception,
        extra=stats.log_extra,
    )

    if not isinstance(stats_attempt.computed_delay, UnsetType) and stats_attempt.computed_delay > 0:
        _ = stats.log.record(
            log_kind="sleep",
            message="Wait %s seconds between attempts.",
            args=(stats_attempt.computed_delay,),
            extra=stats.log_extra,
        )


def default_on_failure(stats: RetryStats) -> None:
    """
    Default ``on_failure`` callback: log the final failure.

    Records a ``"failure"`` message via ``stats.log``, attaching structured
    fields from :attr:`~retry._utils._stats.RetryStats.log_extra`
    to the log record.

    The message distinguishes two cases:

    - all attempts were exhausted;
    - the retry loop was aborted early because the caught exception did
      not match ``retry_on`` or matched ``no_retry_on``.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    if stats_attempt.retry_aborted:
        message = "Retry aborted after %d attempt(s): exception is not retryable."
    else:
        message = "Failed the execution of the function after %d attempts."

    _ = stats.log.record(
        log_kind="failure",
        message=message,
        args=(stats_attempt.retry_index,),
        last_exception=stats_attempt.last_exception,
        extra=stats.log_extra,
    )


def noop_callback(stats: RetryStats) -> None:
    """
    No-op retry callback.

    Used as the resolved value when a user disables a callback by
    passing ``None``. Keeps the invoke path branch-free.

    Parameters
    ----------
    stats : RetryStats
        Unused.

    """
