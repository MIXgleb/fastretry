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
    corresponding default from :mod:`~._utils._callbacks` is used.
    Set a callback explicitly to ``None`` to disable it.

    Attributes
    ----------
    on_success : Callable[[RetryStats], None] | None, optional
        Called after a successful attempt. No default is provided.
    on_retry : Callable[[RetryStats], None] | None, optional
        Called after a failed attempt, before sleeping.
    on_failure : Callable[[RetryStats], None] | None, optional
        Called after all attempts have failed.

    """

    on_success: Callable[[RetryStats], None] | None
    on_retry: Callable[[RetryStats], None] | None
    on_failure: Callable[[RetryStats], None] | None


@dc.dataclass(frozen=True, slots=True)
class ResolvedRetryCallbacks:
    """
    Fully resolved retry callbacks.

    Produced by ``BaseRetrying._resolve_callbacks`` from a user-provided
    :class:`RetryCallbacks` mapping. All keys are present and every value
    is a callable: omitted entries are filled with defaults from
    :mod:`~._utils._callbacks`, and explicit ``None`` values are replaced
    with a no-op callback.

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


def default_on_retry(stats: RetryStats) -> None:
    """
    Default ``on_retry`` callback: log the failed attempt.

    Records a ``"retry"`` message via ``stats.log``, and, when a delay
    is scheduled before the next attempt, also records a ``"sleep"``
    message. Structured fields from :attr:`RetryStats.log_extra` are
    attached to both records.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    _ = stats.log.record(
        log_kind="retry",
        message="Error executing the '%s' function. Try %d of %d.",
        args=(
            stats_attempt.fname,
            stats_attempt.retry_index,
            stats.decorator.attempts,
        ),
        last_exception=stats_attempt.last_exception,
        extra=stats.log_extra,
    )

    if not isinstance(stats_attempt.computed_delay, UnsetType) and stats_attempt.computed_delay > 0:
        _ = stats.log.record(
            log_kind="sleep",
            message="Wait %s seconds between attempts to execute the '%s' function",
            args=(stats_attempt.computed_delay, stats_attempt.fname),
            extra=stats.log_extra,
        )


def default_on_failure(stats: RetryStats) -> None:
    """
    Default ``on_failure`` callback: log the final failure.

    Records a ``"failure"`` message via ``stats.log``, attaching structured
    fields from :attr:`RetryStats.log_extra` to the log record.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    _ = stats.log.record(
        log_kind="failure",
        message="Failed the execution of the '%s' function.",
        args=(stats_attempt.fname,),
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
