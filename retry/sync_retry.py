"""
Synchronous retry decorator.

:class:`~retry.sync_retry.SyncRetrying` wraps regular (non-coroutine)
callables and uses :func:`time.sleep` (or a user-provided sync sleep callable)
between attempts.
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
    Final,
    Unpack,
    override,
)

from retry._types import (
    RetryKwargs,
)
from retry._utils import (
    DelayCalculator,
    RetryStats,
    UnsetType,
)
from retry.base import (
    BaseRetrying,
)


class SyncRetrying[**P, R](BaseRetrying[R, Callable[P, R | UnsetType]]):
    """Sync retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = ("sleep_call",)

    wrapper_kind = "sync"

    @override
    def __init__(self, **kwargs: Unpack[RetryKwargs[R]]) -> None:
        super().__init__(**kwargs)
        self.sleep_call: Final = self._effective_defaults.sync_sleep_call

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
                except BaseException as exc:  # ruff: ignore[blind-except]
                    self._prepare_retry(
                        stats_attempt=stats_attempt,
                        exc=exc,
                        delay_calculator=delay_calculator,
                    )

                    if stats_attempt.retry_aborted:
                        break

                    self._safe_call_callback(callback=on_retry, stats=stats)
                    self._sleep(stats=stats)
                else:
                    self._prepare_success(stats_attempt=stats_attempt, result=result)
                    self._safe_call_callback(callback=on_success, stats=stats)
                    return result

            self._prepare_failure(stats_attempt=stats_attempt)
            self._safe_call_callback(callback=on_failure, stats=stats)
            self._raise_if_needed(stats_attempt=stats_attempt)
            return self.return_default_value

        return wrapper

    @override
    def _sleep(
        self,
        *,
        stats: RetryStats,
    ) -> None:
        stats_attempt = stats.attempt

        if isinstance(stats_attempt.computed_delay, UnsetType) or stats_attempt.computed_delay <= 0:
            return

        try:
            self.sleep_call(stats_attempt.computed_delay)
        except Exception as exc:  # ruff: ignore[blind-except]
            self._log_swallowed(
                operation="sleep callable",
                exc=exc,
                extra=stats.log_extra,
            )

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

    @override
    def _safe_call_callback(
        self,
        *,
        callback: Callable[[RetryStats], Awaitable[None] | None],
        stats: RetryStats,
    ) -> None:
        try:
            self._call_callback(callback=callback, stats=stats)
        except Exception as exc:  # ruff: ignore[blind-except]
            name = getattr(callback, "__name__", "<anonymous>")
            self._log_swallowed(
                operation=f"{name} callback",
                exc=exc,
                extra=stats.log_extra,
            )
