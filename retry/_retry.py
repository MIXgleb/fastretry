"""
Public retry decorator.

This module exposes :func:`retry`, the main entry point of the package.
It dispatches to either :class:`~.sync_retry.SyncRetrying` or
:class:`~.async_retry.AsyncRetrying` depending on whether the decorated
function is a coroutine function.

The decorator can be used in two forms::

    @retry
    def foo() -> int: ...


    @retry(attempts=3, delay=1.0)
    def bar() -> int: ...

"""

import inspect
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    TypeVar,
    Unpack,
    overload,
)

from ._types import (
    UNSET,
    RetryKwargs,
    UnsetType,
)
from .async_retry import (
    AsyncRetrying,
)
from .sync_retry import (
    SyncRetrying,
)

type ReturnType = object
WrappedFunc = TypeVar("WrappedFunc", bound=Callable[..., Awaitable[ReturnType] | ReturnType])


@overload
def retry(func: WrappedFunc) -> WrappedFunc: ...  # ruff: ignore[non-pep695-generic-function]


@overload
def retry(
    *,
    attempts: int | UnsetType = UNSET,
    return_default_value: ReturnType | UnsetType = UNSET,
    delay: float | UnsetType = UNSET,
    disable_all_logging: bool | UnsetType = UNSET,
    re_raise_exception: bool | UnsetType = UNSET,
) -> Callable[[WrappedFunc], WrappedFunc]: ...


def retry[**P, R](  # ruff: ignore[undocumented-param]
    func: Callable[P, R] | None = None,
    **kwargs: Unpack[RetryKwargs[R]],
) -> (
    Callable[P, R]
    | Callable[[Callable[P, R]], Callable[P, R | None] | Callable[P, Awaitable[R | None]]]
):
    """
    Decorate a function to retry it on failure.

    Can be used either as a bare decorator (``@retry``) or called with
    options (``@retry(attempts=3)``). The wrapped function may be
    synchronous or asynchronous; the appropriate retrying strategy is
    selected automatically.

    Options not passed explicitly fall back to the global retry
    defaults (see :func:`~._config.set_retry_defaults`). The factory
    values are listed below.

    Parameters
    ----------
    attempts : int, optional
        Number of attempts (factory default: 1)
    return_default_value : ReturnType, optional
        Default value returned if the function fails after all attempts,
        by default: None
    delay : float, optional
        Delay between attempts in seconds (factory default: 0)
    disable_all_logging : bool, optional
        Disable all logging (factory default: False)
    re_raise_exception : bool, optional
        Re-raise the last intercepted exception after all attempts
        (factory default: True)

    Returns
    -------
    Callable
        A decorator that wraps a function and retries it on failure.


    """
    if func is not None:
        return retry()(func)

    def wrap_async(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        return AsyncRetrying[P, R](**kwargs).wraps(func)

    def wrap_sync(func: Callable[P, R]) -> Callable[P, R | None]:
        return SyncRetrying[P, R](**kwargs).wraps(func)

    def wrap(func: Callable[P, R]) -> Callable[P, R | None] | Callable[P, Awaitable[R | None]]:
        if inspect.iscoroutinefunction(func):
            return wrap_async(func)
        return wrap_sync(func)

    return wrap
