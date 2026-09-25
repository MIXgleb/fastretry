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
    Unpack,
    override,
)

from retry._defaults import (
    defaults,
)
from retry._types import (
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
        self.sleep_call = defaults.sync_sleep_call

    @override
    def _wrap(
        self,
        func: Callable[P, R | UnsetType],
    ) -> Callable[P, R | UnsetType]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | UnsetType:
            intercepted_exception: BaseException | None = None
            fname = getattr(func, "__qualname__", "<anonymous>")
            result = self.return_default_value

            for retry_index in range(1, self.attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    break
                except BaseException as exc:  # ruff: ignore[blind-except]
                    self.exception_block(fname, retry_index, exc)
                    self.sleep_block(fname, retry_index)
                    intercepted_exception = exc
            else:
                self.failed_block(fname, intercepted_exception)

            return result

        return wrapper

    @override
    def sleep_block(
        self,
        fname: str,
        retry_index: int,
    ) -> None:
        if self.delay > 0 and retry_index != self.attempts:
            if (
                not self.disable_logging
                and not self.disable_info_logging
                and self.logger_info is not None
            ):
                self.logger_info(
                    "Wait %s seconds between attempts to execute the '%s' function",
                    self.delay,
                    fname,
                )

            self.sleep_call(self.delay)
