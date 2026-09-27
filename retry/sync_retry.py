"""
Synchronous retry decorator.

``SyncRetrying`` wraps regular (non-coroutine) callables and uses
``time.sleep`` (or a user-provided sync sleep callable) between attempts.
"""

import functools
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
from retry._types import (
    UnsetType,
)
from retry._utils import (
    DelayCalculator,
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
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
            intercepted_exception: Exception | None = None
            fname = getattr(func, "__qualname__", "<anonymous>")
            result = self.return_default_value
            delay_calculator = DelayCalculator(
                delay=self.delay,
                jitter=self.jitter,
            )

            for retry_index in range(1, self.attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    break
                except Exception as exc:  # ruff: ignore[blind-except]
                    self.exception_block(
                        fname=fname,
                        retry_index=retry_index,
                        intercepted_exception=exc,
                    )
                    self.sleep_block(
                        fname=fname,
                        retry_index=retry_index,
                        delay_calculator=delay_calculator,
                    )
                    intercepted_exception = exc
            else:
                self.failed_block(
                    fname=fname,
                    intercepted_exception=intercepted_exception,
                )

            return result

        return wrapper

    @override
    def sleep_block(
        self,
        *,
        delay_calculator: DelayCalculator,
        fname: str,
        retry_index: int,
    ) -> None:
        if retry_index == self.attempts:
            return

        if (computed := delay_calculator.compute(retry_index)) <= 0:
            return

        self._log.record(
            log_kind="sleep",
            message="Wait %s seconds between attempts to execute the '%s' function",
            args=(computed, fname),
        )
        self.sleep_call(computed)
