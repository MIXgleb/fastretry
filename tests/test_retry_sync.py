"""Tests for SyncRetrying decorator."""

import asyncio
import time
import warnings
from typing import (
    Literal,
    NoReturn,
)
from unittest.mock import (
    MagicMock,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

from retry import (
    RetryStats,
)
from retry._config import (
    config,
)
from retry._retry import (
    retry,
)


def test_success_no_retry() -> None:
    calls: list[int] = []

    @retry
    def fn() -> Literal["ok"]:
        calls.append(1)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 1


def test_retry_then_success() -> None:
    calls: list[int] = []

    @retry(attempts=3, delay=0)
    def fn() -> Literal["ok"]:
        calls.append(1)
        if len(calls) < 3:
            msg = "fail"
            raise ValueError(msg)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 3


def test_all_attempts_fail() -> None:
    @retry(attempts=3, delay=0)
    def fn() -> NoReturn:
        msg = "always"
        raise ValueError(msg)

    with pytest.raises(ExceptionGroup) as exc_info:
        fn()
    assert len(exc_info.value.exceptions) == 3


def test_return_default_value() -> None:
    with pytest.warns(
        expected_warning=UserWarning,
        match="return_default_value 42 does not match the declared return type",
    ):

        @retry(attempts=2, delay=0, return_default_value=42)
        def fn() -> NoReturn:
            raise ValueError

    assert fn() == 42


def test_no_return_default_raises() -> None:
    @retry(attempts=1, delay=0)
    def fn() -> NoReturn:
        msg = "boom"
        raise RuntimeError(msg)

    with pytest.raises(ExceptionGroup):
        fn()


def test_args_kwargs_forwarded() -> None:
    @retry(attempts=1, delay=0)
    def fn(a: int, b: int = 2) -> int:
        return a + b

    assert fn(a=1, b=3) == 4


def test_functools_wraps() -> None:
    @retry
    def my_func() -> Literal[1]:
        """Docstring."""  # ruff: ignore[docstring-missing-returns]
        return 1

    assert my_func() == 1
    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "Docstring."


@pytest.mark.parametrize(
    ("retry_on", "no_retry_on", "exc", "expected_calls", "expected_in_group"),
    [
        ((ValueError,), (), TypeError, 1, TypeError),
        ((ValueError,), (), ValueError, 3, ValueError),
        (Exception, (ValueError,), ValueError, 1, ValueError),
        (ValueError, (), ValueError, 3, ValueError),
        (ValueError, (), TypeError, 1, TypeError),
        ((), (ValueError,), ValueError, 1, ValueError),
    ],
)
def test_retry_on_variants(
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    no_retry_on: type[BaseException] | tuple[type[BaseException], ...],
    exc: type[BaseException],
    expected_calls: int,
    expected_in_group: type[BaseException],
) -> None:
    calls: list[int] = []

    @retry(attempts=3, delay=0, retry_on=retry_on, no_retry_on=no_retry_on)
    def fn() -> NoReturn:
        calls.append(1)
        raise exc

    with pytest.raises(ExceptionGroup) as eg:
        fn()

    assert len(calls) == expected_calls
    assert isinstance(eg.value.exceptions[0], expected_in_group)


def test_retry_aborted_flag() -> None:
    captured: list[RetryStats] = []

    @retry(
        attempts=5,
        delay=0,
        no_retry_on=(ValueError,),
        callbacks={"on_failure": captured.append},
    )
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    assert len(captured) == 1
    assert captured[0].attempt.retry_aborted is True
    assert captured[0].attempt.retry_index == 1


def test_delay_applied() -> None:
    start = time.monotonic()

    @retry(attempts=2, delay=0.1)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


def test_on_success_called() -> None:
    cb = MagicMock()

    @retry(attempts=1, delay=0, callbacks={"on_success": cb})
    def fn() -> Literal[1]:
        return 1

    _ = fn()
    cb.assert_called_once()


def test_on_retry_called() -> None:
    cb = MagicMock()

    @retry(attempts=2, delay=0, callbacks={"on_retry": cb})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    assert cb.call_count == 2


def test_on_failure_called() -> None:
    cb = MagicMock()

    @retry(attempts=1, delay=0, callbacks={"on_failure": cb})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    cb.assert_called_once()


def test_async_callback_in_sync() -> None:
    results: list[int] = []

    async def async_cb(_: RetryStats) -> None:
        results.append(1)

    @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
    def fn() -> Literal[1]:
        return 1

    _ = fn()
    assert results == [1]


def test_callback_exception_swallowed() -> None:
    def bad_cb(_: RetryStats) -> NoReturn:
        msg = "callback error"
        raise RuntimeError(msg)

    @retry(attempts=1, delay=0, callbacks={"on_success": bad_cb})
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1


def test_config_retry() -> None:
    config.retry(attempts=5)

    @retry(delay=0)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup) as eg:
        fn()

    assert len(eg.value.exceptions) == 5


def test_context_isolation() -> None:
    config.retry(attempts=1)

    with config.context(attempts=3):

        @retry(delay=0)
        def inner() -> NoReturn:
            raise ValueError

        with pytest.raises(ExceptionGroup) as eg:
            inner()

        assert len(eg.value.exceptions) == 3

    @retry(delay=0)
    def outer() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup) as eg:
        outer()

    assert len(eg.value.exceptions) == 1


def test_disable_warnings_emits_nothing() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        @retry(attempts=0, delay=0, disable_warnings=True)
        def fn() -> Literal[1]:
            return 1

        assert fn() == 1


def test_warnings_emitted_when_not_disabled() -> None:
    with pytest.warns(UserWarning, match="must be >= 1"):

        @retry(attempts=0, delay=0)
        def fn() -> Literal[1]:
            return 1

    assert fn() == 1


def test_async_callback_in_running_loop() -> None:
    async def main() -> None:
        results: list[int] = []

        async def async_cb(_: RetryStats) -> None:
            results.append(1)

        @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
        def fn() -> Literal[1]:
            return 1

        _ = fn()
        assert results == [1]

    asyncio.run(main())


def test_sleep_callable_raises(mocker: MockerFixture) -> None:
    def bad_sleep(_: float) -> None:
        msg = "sleep error"
        raise RuntimeError(msg)

    mock_log_swallowed = mocker.patch("retry.base.BaseRetrying._log_swallowed")
    config.retry(sync_sleep_call=bad_sleep)

    @retry(attempts=2, delay=1)
    def fn() -> Literal[1]:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    mock_log_swallowed.assert_called_once()
    assert mock_log_swallowed.call_args.kwargs["operation"] == "sleep callable"
