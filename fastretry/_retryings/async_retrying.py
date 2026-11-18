"""Asynchronous retry decorator."""

import asyncio
import contextvars
import functools
import inspect
import time
from collections.abc import (
    Callable,
)
from typing import (
    override,
)

from fastretry._compat.aliases import (
    Coro,
    WrappedCoro,
)
from fastretry._compat.functions import (
    is_coroutine_function,
)
from fastretry._compat.sentinels import (
    UnsetType,
)
from fastretry._retryings.base_retrying import (
    BaseRetrying,
)
from fastretry._utils.callbacks import (
    CallbackType,
)
from fastretry._utils.introspection import (
    RetryContext,
)
from fastretry._utils.stats import (
    RetryStats,
)


class AsyncRetrying[**P, R](
    BaseRetrying[
        R,
        Callable[P, R] | Callable[P, Coro[R]],
        Callable[P, WrappedCoro[R]],
    ],
):
    """
    Async retrying decorator for multiple attempts to execute a function in case of an error.

    Supports two kinds of wrapped callables:

    - coroutine functions, which are awaited directly;
    - plain sync functions, which are run in an executor so the event
      loop is not blocked. The executor is chosen by the ``executor``
      option: ``None`` (default) uses the running loop's thread pool;
      an :class:`~concurrent.futures.Executor` instance is passed to
      :meth:`asyncio.AbstractEventLoop.run_in_executor`.

    """

    wrapper_kind = "async"

    @override
    def _wrap(
        self,
        func: Callable[P, R] | Callable[P, Coro[R]],
    ) -> Callable[P, WrappedCoro[R]]:
        on_success = self.callbacks.on_success
        on_retry = self.callbacks.on_retry
        on_failure = self.callbacks.on_failure

        fname = getattr(func, "__qualname__", "<anonymous>")
        invoke = (
            func
            if is_coroutine_function(func)
            else functools.partial(
                self._run_sync_in_executor,
                func,  # pyright: ignore[reportArgumentType]
            )
        )

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
            stats = self._stats.for_call(
                args=args,
                kwargs=kwargs,
                fname=fname,
                started_at=time.monotonic(),
            )
            stats_attempt = stats.attempt

            with RetryContext(stats):
                for retry_index in range(1, self.attempts + 1):
                    stats_attempt.retry_index = retry_index
                    stats_attempt.attempt_started_at = time.monotonic()

                    try:
                        result = await invoke(*args, **kwargs)
                    except BaseException as exc:  # ruff: ignore[blind-except]
                        self._prepare_retry(
                            stats_attempt=stats_attempt,
                            exc=exc,
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

        await asyncio.sleep(stats_attempt.computed_delay)

    @override
    async def _call_callback(
        self,
        *,
        callback: CallbackType,
        stats: RetryStats,
    ) -> None:
        result = callback(stats)

        if inspect.isawaitable(result):
            await result

    @override
    async def _safe_call_callback(
        self,
        *,
        callback: CallbackType,
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

    async def _run_sync_in_executor(
        self,
        func: Callable[P, R],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        executor = self.executor
        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()
        partial = functools.partial(context.run, func, *args, **kwargs)
        return await loop.run_in_executor(executor, partial)
