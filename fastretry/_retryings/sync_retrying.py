"""Synchronous retry decorator."""

import asyncio
import concurrent.futures
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
from fastretry._utils.shared_loop import (
    shared_loop,
)
from fastretry._utils.stats import (
    RetryStats,
)


class SyncRetrying[**P, R](
    BaseRetrying[
        R,
        Callable[P, R],
        Callable[P, R | UnsetType],
    ],
):
    """
    Sync retrying decorator for multiple attempts to execute a function in case of an error.

    Wraps plain sync callables and runs them directly in the calling thread.

    """

    wrapper_kind = "sync"

    @override
    def _wrap(
        self,
        func: Callable[P, R],
    ) -> Callable[P, R | UnsetType]:
        on_success = self.callbacks.on_success
        on_retry = self.callbacks.on_retry
        on_failure = self.callbacks.on_failure

        fname = getattr(func, "__qualname__", "<anonymous>")

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
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
                        result = func(*args, **kwargs)
                    except BaseException as exc:  # ruff: ignore[blind-except]
                        self._prepare_retry(
                            stats_attempt=stats_attempt,
                            exc=exc,
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

        time.sleep(stats_attempt.computed_delay)

    @override
    def _call_callback(
        self,
        *,
        callback: CallbackType,
        stats: RetryStats,
    ) -> None:
        result = callback(stats)

        if not inspect.iscoroutine(result):
            return

        try:
            _ = asyncio.get_running_loop()
            loop_is_running = True
        except RuntimeError:
            loop_is_running = False

        if self._uses_shared_loop(loop_is_running=loop_is_running):
            shared_loop.run_callback(result)
            return

        if loop_is_running:
            context = contextvars.copy_context()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(context.run, asyncio.run, result).result()
            return

        asyncio.run(result)

    def _uses_shared_loop(
        self,
        *,
        loop_is_running: bool,
    ) -> bool:
        mode = self._async_callback_mode

        if mode == "thread_per_call":
            return False

        if mode == "shared_loop_when_running" and not loop_is_running:
            return False

        return not shared_loop.is_owner_thread()

    @override
    def _safe_call_callback(
        self,
        *,
        callback: CallbackType,
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
