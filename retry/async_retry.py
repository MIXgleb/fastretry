"""
Asynchronous retry decorator.

:class:`~retry.async_retry.AsyncRetrying` wraps coroutine
functions and uses :func:`asyncio.sleep`
(or a user-provided async sleep callable) between attempts.
"""

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

from retry._defaults import (
    defaults,
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


class AsyncRetrying[**P, R](BaseRetrying[R, Callable[P, Awaitable[R | UnsetType]]]):
    """Async retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = ("sleep_call",)

    wrapper_kind = "async"

    @override
    def __init__(self, **kwargs: Unpack[RetryKwargs[R]]) -> None:
        super().__init__(**kwargs)
        self.sleep_call: Final = defaults.async_sleep_call

    @override
    def _wrap(
        self,
        func: Callable[P, Awaitable[R | UnsetType]],
    ) -> Callable[P, Awaitable[R | UnsetType]]:
        on_success = self._callbacks.on_success
        on_retry = self._callbacks.on_retry
        on_failure = self._callbacks.on_failure
        delay_calculator = DelayCalculator(
            delay=self.delay,
            jitter=self.jitter,
        )

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
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
                    result = await func(*args, **kwargs)
                except BaseException as exc:  # ruff: ignore[blind-except]
                    self._prepare_retry(
                        stats_attempt=stats_attempt,
                        exc=exc,
                        delay_calculator=delay_calculator,
                    )

                    if stats_attempt.retry_aborted:
                        break

                    await self._safe_call_callback(callback=on_retry, stats=stats)
                    await self._sleep(stats=stats)
                else:
                    self._prepare_success(stats_attempt=stats_attempt, result=result)
                    await self._safe_call_callback(callback=on_success, stats=stats)
                    return result

            self._prepare_failure(stats_attempt=stats_attempt)
            await self._safe_call_callback(callback=on_failure, stats=stats)
            self._raise_if_needed(stats_attempt=stats_attempt)
            return self.return_default_value

        return async_wrapper

    @override
    async def _sleep(
        self,
        *,
        stats: RetryStats,
    ) -> None:
        stats_attempt = stats.attempt

        if isinstance(stats_attempt.computed_delay, UnsetType) or stats_attempt.computed_delay <= 0:
            return

        try:
            await self.sleep_call(stats_attempt.computed_delay)
        except Exception as exc:  # ruff: ignore[blind-except]
            self._log_swallowed(
                operation="sleep callable",
                exc=exc,
                extra=stats.log_extra,
            )

    @override
    async def _call_callback(
        self,
        *,
        callback: Callable[[RetryStats], Awaitable[None] | None],
        stats: RetryStats,
    ) -> None:
        result = callback(stats)

        if inspect.isawaitable(result):
            await result

    @override
    async def _safe_call_callback(
        self,
        *,
        callback: Callable[[RetryStats], Awaitable[None] | None],
        stats: RetryStats,
    ) -> None:
        try:
            await self._call_callback(callback=callback, stats=stats)
        except Exception as exc:  # ruff: ignore[blind-except]
            name = getattr(callback, "__name__", "<anonymous>")
            self._log_swallowed(
                operation=f"{name} callback",
                exc=exc,
                extra=stats.log_extra,
            )
