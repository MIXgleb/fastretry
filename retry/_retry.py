"""
Public retry decorators.

This module exposes two entry points:

- :func:`~retry._retry.retry` — the main decorator, dispatches to
  :class:`~retry.sync_retry.SyncRetrying` or
  :class:`~retry.async_retry.AsyncRetrying` depending on whether the
  decorated function is a coroutine function.
- :func:`~retry._retry.retry_async` — always returns a coroutine
  function; sync callables are run in an executor, coroutine functions
  are awaited directly.

``retry`` can be used in two forms::

    @retry
    def foo() -> int: ...


    @retry(attempts=3, delay=1.0)
    def bar() -> int: ...

"""

from collections.abc import (
    Callable,
)
from concurrent.futures import (
    Executor,
)
from types import (
    CoroutineType,
)
from typing import (
    Any,
    TypeVar,
    Unpack,
    overload,
)

from retry._types import (
    RetryKwargs,
    RetryWithExecutorKwargs,
)
from retry._utils import (
    UNSET,
    CoroType,
    Delay,
    JitterStrategy,
    RetryCallbacks,
    UnsetType,
    is_coroutine_function,
)
from retry.async_retry import (
    AsyncRetrying,
    WrappedCoroType,
)
from retry.sync_retry import (
    SyncRetrying,
)

type _RetryOnType = type[BaseException] | tuple[type[BaseException], ...]
type _ReturnType = object
_WrappedFunc = TypeVar("_WrappedFunc", bound=Callable[..., _ReturnType])


@overload
def retry(func: _WrappedFunc, /) -> _WrappedFunc: ...  # ruff: ignore[non-pep695-generic-function]


@overload
def retry(
    *,
    attempts: int | UnsetType = UNSET,
    return_default_value: _ReturnType | UnsetType = UNSET,
    delay: Delay | UnsetType = UNSET,
    jitter: JitterStrategy | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
    retry_on: _RetryOnType | UnsetType = UNSET,
    no_retry_on: _RetryOnType | UnsetType = UNSET,
    callbacks: RetryCallbacks | UnsetType | None = UNSET,
) -> Callable[[_WrappedFunc], _WrappedFunc]: ...


def retry[**P, R](  # ruff: ignore[undocumented-param]
    func: Callable[P, R] | Callable[P, CoroType[R]] | None = None,
    /,
    **kwargs: Unpack[RetryKwargs[R]],
) -> (
    Callable[P, R | UnsetType]
    | Callable[P, WrappedCoroType[R]]
    | Callable[
        [Callable[P, R] | Callable[P, CoroType[R]]],
        Callable[P, R | UnsetType] | Callable[P, WrappedCoroType[R]],
    ]
):
    """
    Decorate a function to retry it on failure.

    Can be used either as a bare decorator (``@retry``) or called with
    options (``@retry(attempts=3)``). The wrapped function may be
    synchronous or asynchronous; the appropriate retrying strategy is
    selected automatically.

    To run a sync function in an executor from async code, use
    :func:`~retry._retry.retry_async` instead.

    Options not passed explicitly fall back to the global retry
    defaults (see :attr:`~retry._config.config.retry`). The factory
    values are listed below.

    Parameters
    ----------
    attempts : int, ``optional``
        Number of attempts (factory default: 1).
    return_default_value : Any, ``optional``
        Default value returned if the function fails after all attempts.
        When provided, the wrapper returns it instead of re-raising the
        last exception.
    delay : Delay, ``optional``
        Delay between attempts in seconds. A plain ``float`` gives a
        fixed delay (factory default: 0); an
        :class:`~retry._utils._delay.ExponentialDelay` enables exponential
        backoff with ``backoff_factor=2.0`` and no upper bound.
    jitter : JitterStrategy, ``optional``
        Jitter strategy for the delay. When omitted, the default for
        the configured delay type is used (``"none"`` for exponential,
        ``"none"`` for fixed).
    disable_logging : bool, ``optional``
        Disable all logging (factory default: False).
    disable_warnings : bool, ``optional``
        Disable all warnings (factory default: False).
    retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
        Exception types that trigger a retry. Defaults to ``Exception``.
    no_retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
        Exception types that are never retried, even if they match
        ``retry_on``. Takes precedence. Defaults to ``()``.
    callbacks : RetryCallbacks | None, ``optional``
        Mapping of retry lifecycle callbacks. Keys are ``"on_retry"``,
        ``"on_success"``, and ``"on_failure"``; each value is a callable
        ``(stats: RetryStats) -> None`` or ``None`` to disable that event.
        Callbacks may be synchronous or asynchronous.

        You may pass a plain ``dict`` with any subset of these keys, or
        build a :class:`~retry._utils._callbacks.RetryCallbacks` instance
        directly. Pass ``None`` for the whole mapping to disable every
        callback.

        Omitted keys fall back to the defaults. Passing ``None`` for
        a key disables the callback for that event.

        Async callbacks are handled differently depending on the wrapped
        function:

        - On a coroutine function, they are awaited in the same event loop
          (cheap).
        - On a regular function, they are executed synchronously: via
          :func:`asyncio.run` when no event loop is running (cheap), or in
          a separate thread with its own loop when a loop is already
          running (expensive — it blocks the caller until the callback
          completes).

        The latter case is a deliberate trade-off: mixing async callbacks
        with sync functions inside a running event loop is supported, but
        costs a thread per invocation. Prefer synchronous callbacks for
        sync functions, or move the async work outside the retry cycle.

    Returns
    -------
    Callable
        A decorator that wraps a function and retries it on failure.

    Notes
    -----
    **Failure handling**

    When all attempts fail:

    - If ``return_default_value`` is provided, the wrapper returns it.
    - Otherwise, the wrapper raises an exception group containing every
      exception from every attempt, in the order they were raised. A
      single failed attempt still produces a group with one member, so
      the failure type is always the same.

    By default, ``retry_on`` is ``Exception`` and ``no_retry_on`` is
    ``()``, so every caught exception is a subclass of :exc:`Exception`
    and the wrapper raises a standard :exc:`ExceptionGroup`. Catch it
    with ``except* Exception``::

        try:
            foo()
        except* ValueError as eg:
            for exc in eg.exceptions:
                ...

    Exceptions that are **not** matched by ``retry_on`` (or are matched
    by ``no_retry_on``) are not retried. With the default configuration
    this means all :exc:`BaseException` subclasses — such as
    ``KeyboardInterrupt``, ``SystemExit``, and
    ``asyncio.CancelledError`` — propagate immediately: the retry loop
    stops, ``on_retry`` callback is not invoked, and the failure-handling
    path runs (``on_failure`` callback, then re-raise or return
    ``return_default_value``).

    .. warning::

        Passing a :exc:`BaseException` subclass (such as
        ``KeyboardInterrupt`` or ``SystemExit``) in ``retry_on`` or
        ``no_retry_on`` is **not recommended**. If such an exception is
        actually caught, the wrapper raises a
        :exc:`BaseExceptionGroup` instead of an
        :exc:`ExceptionGroup`, and ``except* Exception`` will **not**
        catch it. In that case use ``except* BaseException``::

            try:
                foo()
            except* BaseException as eg:
                for exc in eg.exceptions:
                    ...

        If you are unsure whether a ``BaseException`` subclass might
        end up in the caught set, prefer ``except* BaseException`` — it
        catches both :exc:`ExceptionGroup` and
        :exc:`BaseExceptionGroup`.

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

    def wrap(
        func: Callable[P, R] | Callable[P, CoroType[R]],
    ) -> Callable[P, R | UnsetType] | Callable[P, WrappedCoroType[R]]:
        if is_coroutine_function(func):
            return AsyncRetrying[P, R](**kwargs).wraps(func)
        return SyncRetrying[P, R](**kwargs).wraps(func)  # pyright: ignore[reportArgumentType]

    if func is not None:
        return wrap(func)
    return wrap


@overload
def retry_async[**P, R](
    func: Callable[P, R] | Callable[P, CoroType[R]],
    /,
) -> Callable[P, CoroutineType[Any, Any, R]]: ...


@overload
def retry_async[**P, R](
    *,
    attempts: int | UnsetType = UNSET,
    return_default_value: R | UnsetType = UNSET,
    delay: Delay | UnsetType = UNSET,
    jitter: JitterStrategy | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
    retry_on: _RetryOnType | UnsetType = UNSET,
    no_retry_on: _RetryOnType | UnsetType = UNSET,
    callbacks: RetryCallbacks | UnsetType | None = UNSET,
    executor: Executor | UnsetType = UNSET,
) -> Callable[
    [Callable[P, R] | Callable[P, CoroType[R]]],
    Callable[P, CoroutineType[Any, Any, R]],
]: ...


def retry_async[**P, R](  # ruff: ignore[undocumented-param]
    func: Callable[P, R] | Callable[P, CoroType[R]] | None = None,
    /,
    **kwargs: Unpack[RetryWithExecutorKwargs[R]],
) -> (
    Callable[P, WrappedCoroType[R]]
    | Callable[
        [Callable[P, R] | Callable[P, CoroType[R]]],
        Callable[P, WrappedCoroType[R]],
    ]
):
    """
    Decorate a function to run it asynchronously with retries.

    The decorator always returns a coroutine function: callers must
    ``await`` the result. The wrapped callable may be:

    - a coroutine function, which is awaited directly;
    - a sync function, which is run in an executor so the event loop is
      not blocked.

    For sync functions, this is equivalent to writing::

        @retry(attempts=3)
        async def fn(*args, **kwargs):
            executor: Executor = ...
            loop = asyncio.get_running_loop()
            partial = functools.partial(blocking_io, *args, **kwargs)
            return await loop.run_in_executor(executor, partial)

    but without the boilerplate and with copied context.

    Options not passed explicitly fall back to the global retry
    defaults (see :attr:`~retry._config.config.retry`). The factory
    values are listed below.

    Parameters
    ----------
    attempts : int, ``optional``
        Number of attempts (factory default: 1).
    return_default_value : Any, ``optional``
        Default value returned if the function fails after all attempts.
        When provided, the wrapper returns it instead of re-raising the
        last exception.
    delay : Delay, ``optional``
        Delay between attempts in seconds. A plain ``float`` gives a
        fixed delay (factory default: 0); an
        :class:`~retry._utils._delay.ExponentialDelay` enables exponential
        backoff with ``backoff_factor=2.0`` and no upper bound.
    jitter : JitterStrategy, ``optional``
        Jitter strategy for the delay. When omitted, the default for
        the configured delay type is used (``"none"`` for exponential,
        ``"none"`` for fixed).
    disable_logging : bool, ``optional``
        Disable all logging (factory default: False).
    disable_warnings : bool, ``optional``
        Disable all warnings (factory default: False).
    retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
        Exception types that trigger a retry. Defaults to ``Exception``.
    no_retry_on : type[BaseException] | tuple[type[BaseException], ...], ``optional``
        Exception types that are never retried, even if they match
        ``retry_on``. Takes precedence. Defaults to ``()``.
    callbacks : RetryCallbacks | None, ``optional``
        Mapping of retry lifecycle callbacks, same as in
        :func:`~retry._retry.retry`.
    executor : Executor | None, ``optional``
        Executor used to run sync functions in an async context.
        When omitted (``UNSET``), the running loop's default thread
        pool is used. Pass an :class:`~concurrent.futures.Executor`
        instance to run sync functions via
        :meth:`asyncio.AbstractEventLoop.run_in_executor`. Ignored for
        coroutine functions.

    Returns
    -------
    Callable
        A decorator that wraps a callable into a coroutine function with
        retries.

    Notes
    -----
    See :func:`~retry._retry.retry` for failure handling and exception
    group semantics. This decorator only changes how the wrapped
    callable is invoked, not how retries are handled.

    """

    def wrap(
        _func: Callable[P, R] | Callable[P, CoroType[R]],
    ) -> Callable[P, WrappedCoroType[R]]:
        return AsyncRetrying[P, R](**kwargs).wraps(_func)

    if func is not None:
        return wrap(func)
    return wrap
