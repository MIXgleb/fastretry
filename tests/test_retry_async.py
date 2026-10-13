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
from pytest_mock import (
    MockerFixture,
)

from retry._config import (
    config,
)
from retry._retry import (
    retry,
    retry_async,
)
from retry._utils._stats import (
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

    with pytest.raises(ExceptionGroup) as exc_info:
        await fn()

    assert len(exc_info.value.exceptions) == 2


async def test_return_default_value() -> None:
    with pytest.warns(
        expected_warning=UserWarning,
        match="return_default_value 99 does not match the declared return type",
    ):

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

    with pytest.raises(ExceptionGroup):
        await fn()

    assert len(calls) == expected_calls


async def test_delay_applied() -> None:
    start = time.monotonic()

    @retry(attempts=2, delay=0.05)
    async def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
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

            with pytest.raises(ExceptionGroup) as eg:
                await fn()

            assert len(eg.value.exceptions) == attempts_expected

    _ = await asyncio.gather(task(3), task(5))


async def test_sleep_callable_raises(mocker: MockerFixture) -> None:
    async def bad_sleep(_: float) -> None:
        msg = "sleep error"
        raise RuntimeError(msg)

    mock_log_swallowed = mocker.patch("retry.base.BaseRetrying._log_swallowed")
    config.retry(async_sleep_call=bad_sleep)

    @retry(attempts=2, delay=1)
    async def fn() -> Literal[1]:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        await fn()

    mock_log_swallowed.assert_called_once()
    assert mock_log_swallowed.call_args.kwargs["operation"] == "sleep callable"


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

    with pytest.raises(ExceptionGroup) as eg:
        await fn()

    assert len(eg.value.exceptions) == 2


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
