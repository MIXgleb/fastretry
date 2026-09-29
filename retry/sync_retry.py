"""
Synchronous retry decorator.

``SyncRetrying`` wraps regular (non-coroutine) callables and uses
``time.sleep`` (or a user-provided sync sleep callable) between attempts.
"""

import asyncio
import concurrent.futures
import functools
import inspect
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    TYPE_CHECKING,
    Final,
    Unpack,
    override,
)

from retry._defaults import (
    defaults,
)
from retry._utils import (
    AttemptState,
    DelayCalculator,
    RetryStats,
    UnsetType,
)
from retry.base import (
    BaseRetrying,
)

if TYPE_CHECKING:
    from retry._types import (
        RetryKwargs,
    )


class SyncRetrying[**P, R](BaseRetrying[R, Callable[P, R | UnsetType]]):
    """Sync retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = ("sleep_call",)

    @override
    def __init__(self, **kwargs: Unpack[RetryKwargs[R]]) -> None:
        super().__init__(**kwargs)
        self.sleep_call: Final = defaults.sync_sleep_call

    @override
    def _wrap(
        self,
        func: Callable[P, R | UnsetType],
    ) -> Callable[P, R | UnsetType]:
        on_success = self._callbacks.on_success
        on_retry = self._callbacks.on_retry
        on_failure = self._callbacks.on_failure
        delay_calculator = DelayCalculator(
            delay=self.delay,
            jitter=self.jitter,
        )

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
            stats = self._stats.for_call(
                args=args,
                kwargs=kwargs,
                fname=getattr(func, "__qualname__", "<anonymous>"),
                started_at=time.monotonic(),
            )
            stats_attempt = stats.attempt

            for retry_index in range(1, self.attempts + 1):
                stats_attempt.retry_index = retry_index

                try:
                    result = func(*args, **kwargs)
                except Exception as exc:  # ruff: ignore[blind-except]
                    self._prepare_retry(
                        stats_attempt=stats_attempt,
                        exc=exc,
                        delay_calculator=delay_calculator,
                    )
                    self._call_callback(callback=on_retry, stats=stats)
                    self._sleep(stats_attempt=stats_attempt)
                else:
                    self._prepare_success(stats_attempt=stats_attempt, result=result)
                    self._call_callback(callback=on_success, stats=stats)
                    return result

            self._prepare_failure(stats_attempt=stats_attempt)
            self._call_callback(callback=on_failure, stats=stats)
            self._raise_if_needed(stats_attempt=stats_attempt)
            return self.return_default_value

        return wrapper

    @override
    def _sleep(
        self,
        *,
        stats_attempt: AttemptState,
    ) -> None:
        if stats_attempt.retry_index == self.attempts:
            return

        if isinstance(stats_attempt.computed_delay, UnsetType) or stats_attempt.computed_delay <= 0:
            return

        self._log.record(
            log_kind="sleep",
            message="Wait %s seconds between attempts to execute the '%s' function",
            args=(stats_attempt.computed_delay, stats_attempt.fname),
        )
        self.sleep_call(stats_attempt.computed_delay)

    @override
    def _call_callback(
        self,
        *,
        callback: Callable[[RetryStats], Awaitable[None] | None],
        stats: RetryStats,
    ) -> None:
        result = callback(stats)

        if not inspect.iscoroutine(result):
            return

        try:
            _ = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, result)
                future.result()
