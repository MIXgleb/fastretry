"""
Retry decorator for synchronous and asynchronous functions.

Exposes :func:`retry`, which dispatches to
:class:`~fastretry._retryings.sync_retrying.SyncRetrying` or
:class:`~fastretry._retryings.async_retrying.AsyncRetrying` depending on whether the
decorated function is a coroutine function.

``retry`` can be used in two forms::

    @retry
    def foo() -> int: ...


    @retry(attempts=3, delay=1.0)
    def bar() -> int: ...

"""

from collections.abc import (
    Callable,
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
from fastretry._compat.functions import (
    is_coroutine_function,
)
from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._compat.types import (
    RetryKwargs,
)
from fastretry._retryings.async_retrying import (
    AsyncRetrying,
)
from fastretry._retryings.sync_retrying import (
    SyncRetrying,
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


class _RetryDecorator(Protocol):
    """
    Decorator returned by :func:`~fastretry.retry` when options are provided.

    Preserves the signature and the return type of the wrapped callable,
    whether it is synchronous or asynchronous.

    """

    @overload
    def __call__[**P, R](self, func: Callable[P, Coro[R]]) -> Callable[P, CoroType[R]]: ...

    @overload
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R]: ...


class _RetryDecoratorWithDefault[D](Protocol):
    """
    Decorator returned when ``return_default_value`` is provided.

    The return type of the wrapped callable is widened with the type of the
    default value, so callers see ``R | D`` instead of ``R``. Works for
    synchronous and asynchronous callables.

    """

    @overload
    def __call__[**P, R](self, func: Callable[P, Coro[R]]) -> Callable[P, CoroType[R | D]]: ...

    @overload
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R | D]: ...


@overload
def retry[F: Callable[..., object]](func: F, /) -> F: ...


@overload
def retry[D](
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
) -> _RetryDecoratorWithDefault[D]: ...


@overload
def retry(
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
) -> _RetryDecorator: ...


def retry[**P, R](
    func: Callable[P, R] | Callable[P, CoroType[R]] | None = None,
    /,
    **kwargs: Unpack[RetryKwargs[R]],
) -> object:
    """
    Decorate a function to retry it on failure.

    Can be used either as a bare decorator (``@retry``) or called with
    options (``@retry(attempts=3)``). The wrapped function may be
    synchronous or asynchronous; the appropriate retrying strategy is
    selected automatically.

    To run a sync function in an executor from async code, use
    :func:`~fastretry.retry_async` instead.

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
        Mapping of retry lifecycle callbacks. Keys are ``"on_retry"``,
        ``"on_success"``, and ``"on_failure"``; each value is a callable
        ``(stats: RetryStats) -> None`` or ``None`` to disable that event.
        Callbacks may be synchronous or asynchronous.

        You may pass a plain ``dict`` with any subset of these keys, or
        build a :class:`~fastretry.callbacks.RetryCallbacks` instance
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

        The latter case is a deliberate default: every callback gets a fresh
        thread and a fresh event loop, so failures stay isolated and nothing
        leaks, but it blocks the caller and costs roughly 3 ms per
        invocation (thread and loop creation included). The caller's
        :mod:`contextvars` are copied into the callback, so logging and
        tracing context is preserved.

        For callback-heavy code this cost can be reduced with
        ``config.retry(async_callback_mode=...)``:

        - ``"thread_per_call"`` (default) — the behaviour described above;
        - ``"shared_loop_when_running"`` — a process-wide shared loop replaces the
          per-call thread when an event loop is already running (about 0.1 ms
          per callback);
        - ``"shared_loop_always"`` — the shared loop is used in every case.

        Shared modes serialize callbacks in one daemon thread and share its
        lifecycle across the process: one slow callback delays the others,
        and the loop is recreated after ``fork()``. When in doubt, prefer
        synchronous callbacks for sync functions, or move the async work
        outside the retry cycle.

    Returns
    -------
    Callable
        A decorator that wraps a function and retries it on failure.

    Notes
    -----
    **Option validation**

    Keyword arguments are validated when the decorator is created:
    unknown options, options that exist only globally, and options that this
    decorator does not support raise :exc:`TypeError` immediately. Options
    that only exist globally point at ``config.retry(...)`` or
    ``config.logging(...)``. Invalid option values raise :exc:`TypeError` or
    :exc:`ValueError` when the decorator is applied to a function.

    **Failure handling**

    When all attempts fail:

    - If ``return_default_value`` is provided, the wrapper returns it.
    - Otherwise, the wrapper raises an exception group containing every
      exception from every attempt, in the order they were raised. A
      single failed attempt still produces a group with one member, so
      the failure type is always the same.

    Set ``config.retry(unwrap_single_exception=True)`` to re-raise a
    failure with exactly one collected exception as is, without wrapping
    it in a group. Two or more collected exceptions still produce a group.
    This is handy when migrating from libraries that re-raise the original
    exception.

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

    An aborted exception that is **not** an :exc:`Exception` subclass is
    always re-raised unchanged, even when ``return_default_value`` is set:
    ``KeyboardInterrupt``, ``SystemExit``, ``GeneratorExit`` and
    ``asyncio.CancelledError`` keep the meaning the interpreter and the
    event loop rely on. Grouping ``CancelledError`` would leave the task
    uncancelled, so :func:`asyncio.timeout`, :func:`asyncio.wait_for` and
    structured-concurrency helpers would stop working.

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

    The relation between ``return_default_value`` and the return type of
    the wrapped function is expressed statically: the decorator widens the
    return type with the type of the default value, so type checkers see
    ``R | D`` instead of ``R``::

        @retry(return_default_value=None)
        def fetch() -> bytes: ...


        reveal_type(fetch)  # (…) -> bytes | None

    The check is static only: values that are untyped or come through
    ``Any`` are not verified at runtime.

    """

    def wrap(
        func: Callable[P, R] | Callable[P, Coro[R]],
    ) -> Callable[P, R | UnsetType] | Callable[P, WrappedCoro[R]]:
        if is_coroutine_function(func):
            return AsyncRetrying[P, R](**kwargs).wraps(func)
        return SyncRetrying[P, R](**kwargs).wraps(func)  # pyright: ignore[reportArgumentType]

    validate_decorator_kwargs(
        kwargs=kwargs,
        decorator_name="retry",
    )

    if func is not None:
        return wrap(func)
    return wrap
