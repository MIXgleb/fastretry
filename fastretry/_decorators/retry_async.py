"""
Async retry decorator.

Exposes :func:`retry_async`, which always returns a coroutine function: sync
callables are run in an executor, coroutine functions are awaited directly.

Use :func:`~fastretry.retry` for ordinary coroutine functions: it awaits them
without a thread hop. ``retry_async`` is meant mainly for sync callables that
must not block the event loop.

``retry_async`` can be used in two forms::

    @retry_async
    def foo() -> int: ...


    @retry_async(attempts=3, delay=1.0)
    def bar() -> int: ...

"""

from collections.abc import (
    Callable,
)
from concurrent.futures import (
    Executor,
)
from typing import (
    Protocol,
    Unpack,
    overload,
)

from fastretry._compat.aliases import (
    Coro,
    CoroType,
    RetryOnExceptionType,
    WrappedCoro,
)
from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._compat.types import (
    RetryWithExecutorKwargs,
)
from fastretry._retryings.async_retrying import (
    AsyncRetrying,
)
from fastretry._utils.callbacks import (
    RetryCallbacks,
)
from fastretry._utils.delays import (
    Delay,
    JitterStrategy,
)
from fastretry._utils.validations import (
    validate_decorator_kwargs,
)


class _RetryAsyncDecorator(Protocol):
    """
    Decorator returned by :func:`~fastretry.retry_async` when options are provided.

    Always produces a coroutine function, whether the wrapped callable is
    synchronous or asynchronous.

    """

    @overload
    def __call__[**P, R](self, func: Callable[P, Coro[R]]) -> Callable[P, CoroType[R]]: ...

    @overload
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, CoroType[R]]: ...


class _RetryAsyncDecoratorWithDefault[D](Protocol):
    """
    Async decorator returned when ``return_default_value`` is provided.

    The awaited result type is widened with the type of the default value,
    so callers see ``R | D`` instead of ``R``.

    """

    @overload
    def __call__[**P, R](self, func: Callable[P, Coro[R]]) -> Callable[P, CoroType[R | D]]: ...

    @overload
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, CoroType[R | D]]: ...


@overload
def retry_async[**P, R](
    func: Callable[P, Coro[R]],
    /,
) -> Callable[P, CoroType[R]]: ...


@overload
def retry_async[**P, R](
    func: Callable[P, R],
    /,
) -> Callable[P, CoroType[R]]: ...


@overload
def retry_async[D](
    *,
    return_default_value: D,
    attempts: int | UnsetType = UNSET,
    delay: Delay | UnsetType = UNSET,
    jitter: JitterStrategy | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
    retry_on: RetryOnExceptionType | UnsetType = UNSET,
    no_retry_on: RetryOnExceptionType | UnsetType = UNSET,
    callbacks: RetryCallbacks | UnsetType | None = UNSET,
    executor: Executor | UnsetType = UNSET,
) -> _RetryAsyncDecoratorWithDefault[D]: ...


@overload
def retry_async(
    *,
    attempts: int | UnsetType = UNSET,
    return_default_value: UnsetType = UNSET,
    delay: Delay | UnsetType = UNSET,
    jitter: JitterStrategy | UnsetType = UNSET,
    disable_logging: bool | UnsetType = UNSET,
    disable_warnings: bool | UnsetType = UNSET,
    retry_on: RetryOnExceptionType | UnsetType = UNSET,
    no_retry_on: RetryOnExceptionType | UnsetType = UNSET,
    callbacks: RetryCallbacks | UnsetType | None = UNSET,
    executor: Executor | UnsetType = UNSET,
) -> _RetryAsyncDecorator: ...


def retry_async[**P, R](
    func: Callable[P, R] | Callable[P, CoroType[R]] | None = None,
    /,
    **kwargs: Unpack[RetryWithExecutorKwargs[R]],
) -> object:
    """
    Decorate a function to run it asynchronously with retries.

    The decorator always returns a coroutine function: callers must
    ``await`` the result. The wrapped callable may be:

    - a coroutine function, which is awaited directly;
    - a sync function, which is run in an executor so the event loop is
      not blocked.

    For ordinary coroutine functions prefer :func:`~fastretry.retry`: it
    awaits them directly and also returns a coroutine function.
    ``retry_async`` is meant mainly for **sync** callables that must not
    block the event loop. When one decorator is wanted for both kinds of
    callables, import it under the usual name::

        from fastretry import retry_async as retry

    For sync functions, this is equivalent to writing::

        @retry(attempts=3)
        async def fn(*args, **kwargs):
            executor: Executor = ...
            loop = asyncio.get_running_loop()
            partial = functools.partial(blocking_io, *args, **kwargs)
            return await loop.run_in_executor(executor, partial)

    but without the boilerplate and with copied context.

    Options not passed explicitly fall back to the global retry
    defaults (see ``config.retry``). The factory
    values are listed below.

    Parameters
    ----------
    func : Callable | None, ``optional``
        Callable to decorate. When omitted, the decorator itself is
        returned.
    attempts : int, ``optional``
        Number of attempts (factory default: 1). Values below 1 are replaced
        with 1 and reported with a :exc:`UserWarning`, so the function is
        still called once.
    return_default_value : Any, ``optional``
        Default value returned if the function fails after all attempts.
        When provided, the wrapper returns it instead of re-raising the
        last exception.
    delay : Delay, ``optional``
        Delay between attempts in seconds. A plain ``float`` gives a
        fixed delay (factory default: 0); a negative value is replaced with 0
        and reported with a :exc:`UserWarning`. An
        :class:`~fastretry.delays.ExponentialDelay` enables exponential
        backoff with ``backoff_factor=2.0`` and no upper bound; invalid
        parameters raise :exc:`ValueError` when the decorator is applied. A
        :data:`~fastretry.delays.WaitCallable` receives the attempt index and
        the delay used after the previous attempt, and returns the delay for
        that attempt.
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
        :func:`~fastretry.retry`.
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
    See :func:`~fastretry.retry` for failure handling, exception group
    semantics, the typing of ``return_default_value``, and option
    validation. This decorator only changes how the wrapped callable is
    invoked, not how retries are handled.

    """

    def wrap(
        func: Callable[P, R] | Callable[P, Coro[R]],
    ) -> Callable[P, WrappedCoro[R]]:
        return AsyncRetrying[P, R](**kwargs).wraps(func)

    validate_decorator_kwargs(
        kwargs=kwargs,
        decorator_name="retry_async",
        allow_executor=True,
    )

    if func is not None:
        return wrap(func)
    return wrap
