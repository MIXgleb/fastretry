"""Tests for SyncRetrying decorator."""

import asyncio
import contextvars
import threading
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

from fastretry._config import (
    config,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._utils.stats import (
    RetryStats,
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

    with pytest.RaisesGroup(ValueError, ValueError, ValueError):
        fn()


def test_return_default_value() -> None:
    @retry(attempts=2, delay=0, return_default_value=42)
    def fn() -> NoReturn:
        raise ValueError

    assert fn() == 42


def test_no_return_default_raises() -> None:
    @retry(attempts=1, delay=0)
    def fn() -> NoReturn:
        msg = "boom"
        raise RuntimeError(msg)

    with pytest.RaisesGroup(RuntimeError):
        fn()


def test_unwrap_single_exception() -> None:
    config.retry(unwrap_single_exception=True)

    @retry(attempts=1, delay=0)
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="boom"):
        fn()


def test_unwrap_single_exception_multiple_failures() -> None:
    config.retry(unwrap_single_exception=True)

    @retry(attempts=3, delay=0)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError, ValueError):
        fn()


def test_unwrap_single_exception_aborted() -> None:
    config.retry(unwrap_single_exception=True)

    @retry(attempts=5, delay=0, no_retry_on=ValueError)
    def fn() -> NoReturn:
        msg = "not retryable"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="not retryable"):
        fn()


def test_unwrap_single_exception_disabled_by_default() -> None:
    @retry(attempts=1, delay=0)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError):
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

    with pytest.RaisesGroup(*([expected_in_group] * expected_calls)):
        fn()

    assert len(calls) == expected_calls


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

    with pytest.RaisesGroup(ValueError):
        fn()

    assert len(captured) == 1
    assert captured[0].attempt.retry_aborted is True
    assert captured[0].attempt.retry_index == 1


def test_delay_applied() -> None:
    start = time.monotonic()

    @retry(attempts=2, delay=0.1)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
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

    with pytest.RaisesGroup(ValueError, ValueError):
        fn()

    assert cb.call_count == 2


def test_on_failure_called() -> None:
    cb = MagicMock()

    @retry(attempts=1, delay=0, callbacks={"on_failure": cb})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError):
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
    config.retry(attempts=3)

    @retry(delay=0)
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError, ValueError):
        fn()


def test_context_isolation() -> None:
    config.retry(attempts=1)

    with config.context(attempts=3):

        @retry(delay=0)
        def inner() -> NoReturn:
            raise ValueError

        with pytest.RaisesGroup(ValueError, ValueError, ValueError):
            inner()

    @retry(delay=0)
    def outer() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError):
        outer()


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


def test_async_callback_in_running_loop_keeps_contextvars() -> None:
    cv = contextvars.ContextVar("cv", default="<unset>")
    seen: list[str] = []

    async def async_cb(_: RetryStats) -> None:
        seen.append(cv.get())

    @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
    def fn() -> Literal[1]:
        return 1

    async def main() -> None:
        cv.set("request-42")
        _ = fn()

    asyncio.run(main())

    assert seen == ["request-42"]


def test_shared_loop_when_running_uses_loop_thread() -> None:
    config.retry(async_callback_mode="shared_loop_when_running")
    seen: list[str] = []

    async def async_cb(_: RetryStats) -> None:
        seen.append(threading.current_thread().name)

    @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
    def fn() -> Literal[1]:
        return 1

    async def main() -> None:
        _ = fn()

    asyncio.run(main())

    assert seen == ["fastretry-callback-loop"]


def test_shared_loop_when_running_skips_without_loop() -> None:
    config.retry(async_callback_mode="shared_loop_when_running")
    seen: list[str] = []

    async def async_cb(_: RetryStats) -> None:
        seen.append(threading.current_thread().name)

    @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
    def fn() -> Literal[1]:
        return 1

    _ = fn()

    assert seen == [threading.current_thread().name]


def test_shared_loop_always_uses_loop_thread_without_loop() -> None:
    config.retry(async_callback_mode="shared_loop_always")
    seen: list[str] = []

    async def async_cb(_: RetryStats) -> None:
        seen.append(threading.current_thread().name)

    @retry(attempts=1, delay=0, callbacks={"on_success": async_cb})
    def fn() -> Literal[1]:
        return 1

    _ = fn()

    assert seen == ["fastretry-callback-loop"]


def test_shared_loop_reentrant_callback_does_not_deadlock() -> None:
    config.retry(async_callback_mode="shared_loop_always")
    outer: list[int] = []
    inner: list[int] = []

    async def inner_cb(_: RetryStats) -> None:
        inner.append(1)

    async def outer_cb(_: RetryStats) -> None:
        outer.append(1)
        _ = inner_fn()

    @retry(attempts=1, delay=0, callbacks={"on_success": inner_cb})
    def inner_fn() -> Literal[1]:
        return 1

    @retry(attempts=1, delay=0, callbacks={"on_success": outer_cb})
    def outer_fn() -> Literal[1]:
        return 1

    _ = outer_fn()

    assert outer == [1]
    assert inner == [1]


def test_shared_loop_keeps_working_after_base_exception() -> None:
    config.retry(async_callback_mode="shared_loop_always")

    async def stop_cb(_: RetryStats) -> None:
        raise SystemExit(1)

    @retry(attempts=1, delay=0, callbacks={"on_success": stop_cb})
    def fn() -> Literal[1]:
        return 1

    with pytest.raises(SystemExit):
        fn()

    done: list[int] = []

    async def ok_cb(_: RetryStats) -> None:
        done.append(1)

    @retry(attempts=1, delay=0, callbacks={"on_success": ok_cb})
    def ok_fn() -> Literal[1]:
        return 1

    _ = ok_fn()

    assert done == [1]


def test_attempt_durations_are_recorded() -> None:
    calls: list[int] = []
    retries: list[tuple[float, int, float]] = []
    successes: list[tuple[float, int, float]] = []

    def on_retry(stats: RetryStats) -> None:
        attempt = stats.attempt
        retries.append(
            (attempt.attempt_duration, len(attempt.attempt_durations), attempt.total_elapsed),
        )

    def on_success(stats: RetryStats) -> None:
        attempt = stats.attempt
        successes.append(
            (attempt.attempt_duration, len(attempt.attempt_durations), attempt.total_elapsed),
        )

    @retry(attempts=3, delay=0, callbacks={"on_retry": on_retry, "on_success": on_success})
    def fn() -> Literal[1]:
        calls.append(1)
        time.sleep(0.01)
        if len(calls) < 3:
            msg = "fail"
            raise ValueError(msg)
        return 1

    assert fn() == 1

    assert len(retries) == 2
    assert [count for _, count, _ in retries] == [1, 2]
    assert all(duration > 0 for duration, _, _ in retries)
    assert all(total > 0 for _, _, total in retries)

    duration, count, total = successes[0]
    assert count == 3
    assert duration > 0
    assert total > duration


def test_attempt_durations_on_failure() -> None:
    seen: list[tuple[int, float, float]] = []

    def on_failure(stats: RetryStats) -> None:
        attempt = stats.attempt
        durations = attempt.attempt_durations
        seen.append((len(durations), attempt.attempt_duration, durations[-1]))

    @retry(attempts=2, delay=0, callbacks={"on_failure": on_failure})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
        fn()

    assert len(seen) == 1
    count, current, last = seen[0]
    assert count == 2
    assert current == last
    assert current >= 0
