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
    TYPE_CHECKING,
    TypeVar,
    Unpack,
    overload,
)

from retry._utils import (
    UNSET,
    Delay,
    JitterStrategy,
    RetryCallbacks,
    UnsetType,
)
from retry.async_retry import (
    AsyncRetrying,
)
from retry.sync_retry import (
    SyncRetrying,
)

if TYPE_CHECKING:
    from retry._types import (
        RetryKwargs,
    )

type _ReturnType = object
_WrappedFunc = TypeVar("_WrappedFunc", bound=Callable[..., _ReturnType])


@overload
def retry(func: _WrappedFunc) -> _WrappedFunc: ...  # ruff: ignore[non-pep695-generic-function]


@overload
def retry(
    *,
    attempts: int | UnsetType = UNSET,
    return_default_value: _ReturnType | UnsetType = UNSET,
    delay: Delay | UnsetType = UNSET,
    jitter: JitterStrategy | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
    callbacks: RetryCallbacks | UnsetType = UNSET,
) -> Callable[[_WrappedFunc], _WrappedFunc]: ...


def retry[**P, R](  # ruff: ignore[undocumented-param]
    func: Callable[P, R] | None = None,
    **kwargs: Unpack[RetryKwargs[R]],
) -> (
    Callable[P, R]
    | Callable[[Callable[P, R]], Callable[P, R | UnsetType] | Callable[P, Awaitable[R | UnsetType]]]
):
    """
    Decorate a function to retry it on failure.

    Can be used either as a bare decorator (``@retry``) or called with
    options (``@retry(attempts=3)``). The wrapped function may be
    synchronous or asynchronous; the appropriate retrying strategy is
    selected automatically.

    Options not passed explicitly fall back to the global retry
    defaults (see :func:`set_retry_defaults`). The factory
    values are listed below.

    Parameters
    ----------
    attempts : int, optional
        Number of attempts (factory default: 1)
    return_default_value : Any, optional
        Default value returned if the function fails after all attempts.
        When provided, the wrapper returns it instead of re-raising the
        last exception.
    delay : Delay, optional
        Delay between attempts in seconds. A plain ``float`` gives a
        fixed delay (factory default: 0); an ``ExponentialDelay``
        enables exponential backoff with ``backoff_factor=2.0`` and
        no upper bound.
    jitter : JitterStrategy, optional
        Jitter strategy for the delay. When omitted, the default for
        the configured delay type is used (``"none"`` for exponential,
        ``"none"`` for fixed).
    disable_logging : bool, optional
        Disable all logging (factory default: False)
    disable_warnings : bool, optional
        Disable all warnings (factory default: False)
    callbacks : RetryCallbacks, optional
        Mapping of retry lifecycle callbacks. Keys are ``"on_retry"``,
        ``"on_success"``, and ``"on_failure"``; each value is a callable
        ``(stats: RetryStats) -> None`` or ``None`` to disable that event.

        You may pass a plain ``dict`` with any subset of these keys, or
        build a :class:`RetryCallbacks` instance directly.

        Omitted keys fall back to the defaults. Passing ``None`` for
        a key disables the callback for that event.

    Returns
    -------
    Callable
        A decorator that wraps a function and retries it on failure.

    Notes
    -----
    **Interaction between ``return_default_value`` and re-raising**

    - If ``return_default_value`` is provided, the wrapper returns it
      after all attempts fail.
    - If ``return_default_value`` is not provided, the wrapper re-raises
      the last exception.

    **Type checking of ``return_default_value``**

    When ``return_default_value`` is provided, the decorator performs a
    best-effort runtime check that its type matches the declared return type
    of the wrapped function. Only simple types and unions are checked;
    complex generics (``list[int]``, ``dict[str, str]``, ...) and
    unresolvable annotations are skipped silently. A ``UserWarning`` is
    emitted on a confirmed mismatch.

    Because the check is best-effort, always pass a ``return_default_value``
    whose type is compatible with the function's declared return type.

    """
    if func is not None:
        return retry()(func)

    def wrap_async(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | UnsetType]]:
        return AsyncRetrying[P, R](**kwargs).wraps(func)

    def wrap_sync(func: Callable[P, R]) -> Callable[P, R | UnsetType]:
        return SyncRetrying[P, R](**kwargs).wraps(func)

    def wrap(
        func: Callable[P, R],
    ) -> Callable[P, R | UnsetType] | Callable[P, Awaitable[R | UnsetType]]:
        if inspect.iscoroutinefunction(func):
            return wrap_async(func)
        return wrap_sync(func)

    return wrap
