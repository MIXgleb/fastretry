"""
Retry lifecycle callbacks.

Defines the callback mapping accepted by retry decorators, its resolved
counterpart, and the built-in defaults used when no callback is
provided.
"""

import dataclasses as dc
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Final,
    TypedDict,
)

from retry._compat.sentinels import (
    UnsetType,
)
from retry._utils.stats import (
    RetryStats,
)

_PRIMITIVE_TYPES: Final[tuple[type, ...]] = (
    int,
    float,
    complex,
    str,
    bool,
    bytes,
    bytearray,
    type(None),
)

type CallbackType = Callable[[RetryStats], Awaitable[None] | None]


class RetryCallbacks(TypedDict, total=False):
    """
    Callbacks invoked during retry processing.

    All callbacks are optional. When a callback is omitted, the
    corresponding built-in default is used. Set a callback explicitly
    to ``None`` to disable it.

    Attributes
    ----------
    on_success : CallbackType, ``optional``
        Called after a successful attempt.
    on_retry : CallbackType, ``optional``
        Called after a failed attempt, before sleeping.
    on_failure : CallbackType, ``optional``
        Called after all attempts have failed.

    """

    on_success: CallbackType | None
    on_retry: CallbackType | None
    on_failure: CallbackType | None


@dc.dataclass(frozen=True, slots=True)
class ResolvedRetryCallbacks:
    """
    Fully resolved retry callbacks.

    All fields are populated: omitted entries are filled with built-in
    defaults, and explicit ``None`` values are replaced with a no-op.

    Attributes
    ----------
    on_success : CallbackType
        Called after a successful attempt.
    on_retry : CallbackType
        Called after a failed attempt, before sleeping.
    on_failure : CallbackType
        Called after all attempts have failed.

    """

    on_success: CallbackType
    on_retry: CallbackType
    on_failure: CallbackType


def default_on_success(stats: RetryStats) -> None:
    """
    Log the successful attempt.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    result = stats.attempt.result

    if isinstance(result, _PRIMITIVE_TYPES):
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
    Log the failed attempt and, when a delay is scheduled, the sleep.

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
    Log the final failure.

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
    """No-op callback used when a callback is disabled."""
