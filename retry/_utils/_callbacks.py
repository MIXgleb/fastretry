import dataclasses as dc
from typing import (
    TYPE_CHECKING,
    TypedDict,
)

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
    )

    from retry._utils._stats import (
        RetryStats,
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

    Records a ``"retry"`` message via ``stats.log``. If ``logger_retry``
    is ``None`` or logging is disabled, the call is a no-op.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    stats.log.record(
        log_kind="retry",
        message="Error executing the '%s' function. Try %d of %d.",
        args=(
            stats_attempt.fname,
            stats_attempt.retry_index,
            stats.decorator.attempts,
        ),
        last_exception=stats_attempt.last_exception,
    )


def default_on_failure(stats: RetryStats) -> None:
    """
    Default ``on_failure`` callback: log the final failure.

    Records a ``"failure"`` message via ``stats.log``. If ``logger_failure``
    is ``None`` or logging is disabled, the call is a no-op.

    Parameters
    ----------
    stats : RetryStats
        Current retry statistics.

    """
    stats_attempt = stats.attempt

    stats.log.record(
        log_kind="failure",
        message="Failed the execution of the '%s' function.",
        args=(stats_attempt.fname,),
        last_exception=stats_attempt.last_exception,
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
