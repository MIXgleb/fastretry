"""
Synchronous retry decorator.

``SyncRetrying`` wraps regular (non-coroutine) callables and uses
``time.sleep`` (or a user-provided sync sleep callable) between attempts.
"""

import functools
import time
from collections.abc import (
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
    UNSET,
    AttemptState,
    DelayCalculator,
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
            attempt_stats = stats.attempt
            result = self.return_default_value

            for retry_index in range(1, self.attempts + 1):
                attempt_stats.retry_index = retry_index

                try:
                    result = func(*args, **kwargs)
                    attempt_stats.result = result
                    attempt_stats.elapsed = time.monotonic() - attempt_stats.started_at
                    on_success(stats)
                    break
                except Exception as exc:  # ruff: ignore[blind-except]
                    attempt_stats.intercepted_exception = exc
                    attempt_stats.elapsed = time.monotonic() - attempt_stats.started_at
                    attempt_stats.computed_delay = UNSET

                    if retry_index < self.attempts:
                        attempt_stats.computed_delay = delay_calculator.compute(retry_index)

                    on_retry(stats)
                    self.sleep_block(attempt_stats)
            else:
                attempt_stats.elapsed = time.monotonic() - attempt_stats.started_at

                if self.re_raise_exception and attempt_stats.intercepted_exception is not None:
                    on_failure(stats)
                    raise attempt_stats.intercepted_exception

                attempt_stats.result = result
                on_failure(stats)

            return result

        return wrapper

    @override
    def sleep_block(
        self,
        attempt_stats: AttemptState,
    ) -> None:
        if attempt_stats.retry_index == self.attempts:
            return

        if isinstance(attempt_stats.computed_delay, UnsetType) or attempt_stats.computed_delay <= 0:
            return

        self._log.record(
            log_kind="sleep",
            message="Wait %s seconds between attempts to execute the '%s' function",
            args=(attempt_stats.computed_delay, attempt_stats.fname),
        )
        self.sleep_call(attempt_stats.computed_delay)
