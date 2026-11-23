"""
Interruption and cancellation must keep their meaning.

``KeyboardInterrupt``, ``SystemExit``, ``GeneratorExit`` and
:exc:`asyncio.CancelledError` are not :exc:`Exception` subclasses: wrapping
them in an exception group, or replacing them with ``return_default_value``,
breaks the protocol the interpreter and the event loop rely on.
"""

import asyncio
from typing import (
    Literal,
    NoReturn,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry._retryings.sync_retrying import (
    SyncRetrying,
)
from fastretry._utils.stats import (
    AttemptState,
)
from fastretry.introspection import (
    get_active_runs,
)


def test_keyboard_interrupt_reaches_the_caller() -> None:
    @retry(attempts=3, delay=0)
    def fn() -> NoReturn:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        fn()


def test_system_exit_reaches_the_caller() -> None:
    @retry(attempts=3, delay=0)
    def fn() -> NoReturn:
        code = 3
        raise SystemExit(code)

    with pytest.raises(SystemExit) as exc_info:
        fn()

    assert exc_info.value.code == 3


@pytest.mark.parametrize("exit_code", [None, 0, 2])
def test_system_exit_code_is_preserved(exit_code: int | None) -> None:
    @retry(attempts=2, delay=0)
    def fn() -> NoReturn:
        raise SystemExit(exit_code)

    with pytest.raises(SystemExit) as exc_info:
        fn()

    assert exc_info.value.code == exit_code


def test_interruption_is_not_replaced_by_the_default_value() -> None:
    @retry(attempts=2, delay=0, return_default_value="fallback")
    def fn() -> NoReturn:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        fn()


def test_failure_callback_runs_before_the_interruption_propagates() -> None:
    seen: list[Literal["failure"]] = []

    @retry(
        attempts=2,
        delay=0,
        callbacks={"on_failure": lambda _stats: seen.append("failure")},
    )
    def fn() -> NoReturn:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        fn()

    assert seen == ["failure"]


def test_single_non_retryable_exception_is_still_grouped() -> None:
    @retry(attempts=2, delay=0, retry_on=(TimeoutError,))
    def fn() -> NoReturn:
        msg = "not retryable"
        raise ValueError(msg)

    with pytest.RaisesGroup(ValueError, match="Retry aborted"):
        fn()


def test_aborted_run_leaves_no_registry_entry() -> None:
    @retry(attempts=2, delay=0)
    def fn() -> NoReturn:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        fn()

    assert get_active_runs() == {}


async def test_cancelled_error_is_not_swallowed_by_the_default_value() -> None:
    @retry(attempts=3, delay=0, return_default_value="fallback")
    async def fn() -> NoReturn:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await fn()


async def test_task_cancel_marks_the_task_cancelled() -> None:
    @retry(attempts=3, delay=0)
    async def slow() -> None:
        await asyncio.sleep(5)

    task = asyncio.ensure_future(slow())
    await asyncio.sleep(0.01)
    _ = task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()


async def test_asyncio_timeout_raises_timeout_error() -> None:
    @retry(attempts=3, delay=0)
    async def slow() -> None:
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await slow()


async def test_wait_for_raises_timeout_error() -> None:
    @retry(attempts=3, delay=0)
    async def slow() -> None:
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(slow(), timeout=0.01)


async def test_cancellation_during_the_delay_is_not_retried() -> None:
    calls: list[int] = []

    @retry(attempts=5, delay=5.0)
    async def fn() -> None:
        calls.append(1)
        msg = "retryable"
        raise ValueError(msg)

    task = asyncio.ensure_future(fn())
    await asyncio.sleep(0.01)
    _ = task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == [1]
    assert task.cancelled()


def test_sync_cancelled_error_is_re_raised() -> None:
    @retry(attempts=3, delay=0)
    def fn() -> NoReturn:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        fn()


def test_raise_if_needed_without_exceptions_returns() -> None:
    retrying = SyncRetrying(attempts=2)
    retrying._raise_if_needed(stats_attempt=AttemptState())


def test_raise_if_needed_returns_when_nothing_is_re_raised() -> None:
    retrying = SyncRetrying(attempts=2, return_default_value="default")
    retrying._raise_if_needed(stats_attempt=AttemptState(exceptions=[ValueError("x")]))
