"""
Asynchronous retry decorator.

``AsyncRetrying`` wraps coroutine functions and uses ``asyncio.sleep``
(or a user-provided async sleep callable) between attempts.
"""

import functools
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
from retry._types import (
    UnsetType,
)
from retry._utils import DelayCalculator
from retry.base import (
    BaseRetrying,
)

if TYPE_CHECKING:
    from retry._types import (
        RetryKwargs,
    )


class AsyncRetrying[**P, R](BaseRetrying[R, Callable[P, Awaitable[R | UnsetType]]]):
    """Async retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = ("sleep_call",)

    @override
    def __init__(self, **kwargs: Unpack[RetryKwargs[R]]) -> None:
        super().__init__(**kwargs)
        self.sleep_call: Final = defaults.async_sleep_call

    @override
    def _wrap(
        self,
        func: Callable[P, Awaitable[R | UnsetType]],
    ) -> Callable[P, Awaitable[R | UnsetType]]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
            intercepted_exception: BaseException | None = None
            fname = getattr(func, "__qualname__", "<anonymous>")
            result = self.return_default_value
            delay_calculator = DelayCalculator(
                delay=self.delay,
                jitter=self.jitter,
            )

            for retry_index in range(1, self.attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    break
                except BaseException as exc:  # ruff: ignore[blind-except]
                    self.exception_block(
                        fname=fname,
                        retry_index=retry_index,
                        intercepted_exception=exc,
                    )
                    await self.sleep_block(
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

        return async_wrapper

    @override
    async def sleep_block(
        self,
        *,
        fname: str,
        retry_index: int,
        delay_calculator: DelayCalculator,
    ) -> None:
        if retry_index == self.attempts:
            return

        if (computed := delay_calculator.compute(retry_index)) <= 0:
            return

        self._log.info(
            "Wait %s seconds between attempts to execute the '%s' function",
            computed,
            fname,
        )
        await self.sleep_call(computed)
