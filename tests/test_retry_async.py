"""Tests for AsyncRetrying decorator."""

import asyncio
import contextvars
import time
from concurrent.futures import (
    ThreadPoolExecutor,
)
from typing import (
    Literal,
    NoReturn,
)
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest

from fastretry._config import (
    config,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry._utils.stats import (
    RetryStats,
)


async def test_success() -> None:
    calls: list[int] = []

    @retry
    async def fn() -> Literal["ok"]:
        calls.append(1)
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 1


async def test_retry_then_success() -> None:
    calls: list[int] = []

    @retry(attempts=3, delay=0)
    async def fn() -> Literal["ok"]:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 2


async def test_all_fail() -> None:
    @retry(attempts=2, delay=0)
    async def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
        await fn()


async def test_unwrap_single_exception() -> None:
    config.retry(unwrap_single_exception=True)

    @retry(attempts=1, delay=0)
    async def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="boom"):
        await fn()


async def test_unwrap_single_exception_multiple_failures() -> None:
    config.retry(unwrap_single_exception=True)

    @retry(attempts=2, delay=0)
    async def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
        await fn()


async def test_return_default_value() -> None:
    @retry(attempts=1, delay=0, return_default_value=99)
    async def fn() -> NoReturn:
        raise ValueError

    assert await fn() == 99


@pytest.mark.parametrize(
    ("retry_on", "no_retry_on", "expected_calls"),
    [
        ((Exception,), (), 5),
        ((Exception,), (ValueError,), 1),
        (ValueError, (), 5),
    ],
)
async def test_retry_on_variants(
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    no_retry_on: type[BaseException] | tuple[type[BaseException], ...],
    expected_calls: int,
) -> None:
    calls: list[int] = []

    @retry(attempts=5, delay=0, retry_on=retry_on, no_retry_on=no_retry_on)
    async def fn() -> NoReturn:
        calls.append(1)
        raise ValueError

    with pytest.RaisesGroup(*([ValueError] * expected_calls)):
        await fn()

    assert len(calls) == expected_calls


async def test_delay_applied() -> None:
    start = time.monotonic()

    @retry(attempts=2, delay=0.05)
    async def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
        await fn()

    elapsed = time.monotonic() - start
    assert elapsed >= 0.05


async def test_sync_callback() -> None:
    cb = MagicMock()

    @retry(attempts=1, delay=0, callbacks={"on_success": cb})
    async def fn() -> Literal[1]:
        return 1

    _ = await fn()
    cb.assert_called_once()


async def test_async_callback() -> None:
    cb = AsyncMock()

    @retry(attempts=1, delay=0, callbacks={"on_success": cb})
    async def fn() -> Literal[1]:
        return 1

    _ = await fn()
    cb.assert_awaited_once()


async def test_callback_error_swallowed() -> None:
    async def bad_cb(_: RetryStats) -> None:
        msg = "cb error"
        raise RuntimeError(msg)

    @retry(attempts=1, delay=0, callbacks={"on_success": bad_cb})
    async def fn() -> Literal[1]:
        return 1

    assert await fn() == 1


async def test_context_isolation_between_tasks() -> None:
    config.retry(attempts=1)

    async def task(attempts_expected: int) -> None:
        with config.context(attempts=attempts_expected):
            await asyncio.sleep(0)

            @retry(delay=0)
            async def fn() -> NoReturn:
                raise ValueError

            with pytest.RaisesGroup(*([ValueError] * attempts_expected)):
                await fn()

    _ = await asyncio.gather(task(3), task(5))


async def test_retry_async_sync_function() -> None:
    calls: list[int] = []

    @retry_async(attempts=3, delay=0)
    def fn() -> Literal["ok"]:
        calls.append(1)
        if len(calls) < 2:
            msg = "fail"
            raise ValueError(msg)
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 2


async def test_retry_async_sync_bare_decorator() -> None:
    @retry_async
    def fn() -> Literal[1]:
        return 1

    assert await fn() == 1


async def test_retry_async_sync_callable_explicit() -> None:
    def fn() -> Literal[1]:
        return 1

    wrapped = retry_async(fn)
    assert await wrapped() == 1


async def test_retry_async_async_function() -> None:
    calls: list[int] = []

    @retry_async(attempts=3, delay=0)
    async def fn() -> Literal["ok"]:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError
        return "ok"

    assert await fn() == "ok"
    assert len(calls) == 2


async def test_retry_async_async_bare_decorator() -> None:
    @retry_async
    async def fn() -> Literal[1]:
        return 1

    assert await fn() == 1


async def test_retry_async_all_fail() -> None:
    @retry_async(attempts=2, delay=0)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
        await fn()


async def test_retry_async_with_custom_executor() -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:

        @retry_async(attempts=1, delay=0, executor=pool)
        def fn() -> Literal[1]:
            return 1

        assert await fn() == 1


async def test_retry_async_contextvars_propagated() -> None:
    var: contextvars.ContextVar[str] = contextvars.ContextVar("var")

    @retry_async(attempts=1, delay=0)
    def fn() -> str:
        return var.get()

    token = var.set("hello")
    try:
        assert await fn() == "hello"
    finally:
        var.reset(token)


async def test_retry_async_contextvars_propagated_custom_executor() -> None:
    var: contextvars.ContextVar[str] = contextvars.ContextVar("var")

    with ThreadPoolExecutor(max_workers=1) as pool:

        @retry_async(attempts=1, delay=0, executor=pool)
        def fn() -> str:
            return var.get()

        token = var.set("hello")
        try:
            assert await fn() == "hello"
        finally:
            var.reset(token)


async def test_attempt_durations_are_recorded() -> None:
    seen: list[tuple[int, float]] = []

    def on_success(stats: RetryStats) -> None:
        attempt = stats.attempt
        seen.append((len(attempt.attempt_durations), attempt.attempt_duration))

    @retry(attempts=1, delay=0, callbacks={"on_success": on_success})
    async def fn() -> Literal[1]:
        return 1

    assert await fn() == 1

    assert seen[0][0] == 1
    assert seen[0][1] >= 0
