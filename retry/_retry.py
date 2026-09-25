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
    Any,
    Literal,
    TypeVar,
    Unpack,
    overload,
)

from ._return_type_check import (
    ReturnTypeChecker,
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
WrappedFunc = TypeVar("WrappedFunc", bound=Callable[..., ReturnType])


@overload
def retry(func: WrappedFunc) -> WrappedFunc: ...  # ruff: ignore[non-pep695-generic-function]


@overload
def retry(
    *,
    return_default_value: ReturnType,
    re_raise_exception: Literal[False] = False,
    attempts: int | UnsetType = UNSET,
    delay: float | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
) -> Callable[[WrappedFunc], WrappedFunc]: ...


@overload
def retry(
    *,
    re_raise_exception: Literal[True] = True,
    attempts: int | UnsetType = UNSET,
    delay: float | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
) -> Callable[[WrappedFunc], WrappedFunc]: ...


def retry[**P, R, WrappedFunc: Callable[..., ReturnType]](  # ruff: ignore[undocumented-param]
    func: WrappedFunc | None = None,
    **kwargs: Unpack[RetryKwargs[R]],
) -> (
    WrappedFunc | Callable[[WrappedFunc], Callable[P, R | None] | Callable[P, Awaitable[R | None]]]
):
    # func: Callable[P, R] | None = None,
    # **kwargs: Unpack[RetryKwargs[R]],
    # ) -> (
    #     Callable[P, R]
    #     | Callable[[Callable[P, R]], Callable[P, R | None] | Callable[P, Awaitable[R | None]]]
    # ):
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
    return_default_value : Any, optional
        Default value returned if the function fails after all attempts
    delay : float, optional
        Delay between attempts in seconds (factory default: 0)
    disable_logging : bool, optional
        Disable all logging (factory default: False)
    disable_warnings : bool, optional
        Disable all warnings (factory default: False)
    re_raise_exception : bool, optional
        Re-raise the last intercepted exception after all attempts
        (factory default: True)

    Returns
    -------
    Callable
        A decorator that wraps a function and retries it on failure.

    Notes
    -----
    Interaction between ``return_default_value`` and ``re_raise_exception``:

    - If ``return_default_value`` is provided, the wrapper returns it after
      all attempts fail. ``re_raise_exception=True`` in this case is ignored
      (a warning is emitted).
    - If ``return_default_value`` is not provided, the wrapper re-raises the
      last exception by default. ``re_raise_exception=False`` in this case
      causes ``UNSET`` to be returned (a warning is emitted).
    - Passing ``re_raise_exception=False`` without ``return_default_value``
      is therefore discouraged.

    Type checking of ``return_default_value``:

    When ``return_default_value`` is provided, the decorator performs a
    best-effort runtime check that its type matches the declared return type
    of the wrapped function. Only simple types and ``Optional``-unions are
    checked; complex generics (``list[int]``, ``dict[str, str]``, ...) and
    unresolvable annotations are skipped silently. A ``UserWarning`` is
    emitted on a confirmed mismatch.

    Because the check is best-effort, always pass a ``return_default_value``
    whose type is compatible with the function's declared return type.


    """
    if func is not None:
        return retry()(func)

    def wrap_async(func: WrappedFunc) -> Callable[P, Awaitable[R | UnsetType]]:
        return AsyncRetrying[P, R](**kwargs).wraps(func)

    def wrap_sync(func: WrappedFunc) -> Callable[P, R | UnsetType]:
        return SyncRetrying[P, R](**kwargs).wraps(func)

    def wrap(
        func: WrappedFunc,
    ) -> Callable[P, R | UnsetType] | Callable[P, Awaitable[R | UnsetType]]:
        if inspect.iscoroutinefunction(func):
            return wrap_async(func)
        return wrap_sync(func)

    return wrap

    # def wrap_async(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
    #     return AsyncRetrying[P, R](**kwargs).wraps(func)

    # def wrap_sync(func: Callable[P, R]) -> Callable[P, R | None]:
    #     return SyncRetrying[P, R](**kwargs).wraps(func)

    # def wrap(func: Callable[P, R]) -> Callable[P, R | None] | Callable[P, Awaitable[R | None]]:
    #     if inspect.iscoroutinefunction(func):
    #         return wrap_async(func)
    #     return wrap_sync(func)

    # return wrap
