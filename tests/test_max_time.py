"""The ``max_time`` budget bounds a whole call, not a single attempt."""

import asyncio
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Literal,
    NoReturn,
)

import pytest

from fastretry._configs.config import (
    config,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry._retryings.sync_retrying import (
    SyncRetrying,
)


class FakeClock:
    """Monotonic clock that only advances when something sleeps."""

    def __init__(self) -> None:
        """Start at zero with no sleeps recorded."""
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        """
        Return the elapsed fake time.

        Returns
        -------
        float
            Seconds since the clock was created.

        """
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record a sleep and advance the clock by it."""
        self.sleeps.append(seconds)
        self.now += seconds


def _async_sleep(clock: FakeClock) -> Callable[[float], Awaitable[None]]:
    """
    Build an awaitable sleep that advances ``clock``.

    Parameters
    ----------
    clock : FakeClock
        Clock to advance.

    Returns
    -------
    Callable[[float], Awaitable[None]]
        Awaitable replacement for :func:`asyncio.sleep`.

    """

    async def sleep(seconds: float) -> None:
        clock.sleep(seconds)

    return sleep


def _expect_group(members: int, message: str) -> "pytest.RaisesGroup[ValueError]":
    """
    Expect a group of ``members`` :exc:`ValueError` whose own message is ``message``.

    Parameters
    ----------
    members : int
        Number of collected exceptions.
    message : str
        Message of the exception group.

    Returns
    -------
    pytest.RaisesGroup
        Context manager asserting the group.

    """
    return pytest.RaisesGroup(
        *([ValueError] * members),
        check=lambda group: group.message == message,
    )


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """
    Replace the clocks the retry loop reads.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Patch helper.

    Returns
    -------
    FakeClock
        Clock installed for the test.

    """
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)  # ruff: ignore[shared-clock-mock]
    monkeypatch.setattr(time, "sleep", fake.sleep)  # ruff: ignore[shared-clock-mock]

    return fake


def test_retry_stops_when_the_budget_is_spent(clock: FakeClock) -> None:
    calls: list[int] = []

    @retry(attempts=10, delay=1.0, max_time=5.0)
    def fn() -> NoReturn:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(5, "Time budget of 5s exhausted after 5 attempt(s)"):
        fn()

    assert len(calls) == 5
    assert clock.sleeps == [1.0, 1.0, 1.0, 1.0]
    assert clock.now <= 5.0


def test_success_inside_the_budget_is_returned() -> None:
    calls: list[int] = []

    @retry(attempts=10, delay=1.0, max_time=5.0)
    def fn() -> Literal["ok"]:
        calls.append(1)

        if len(calls) < 3:
            msg = "boom"
            raise ValueError(msg)

        return "ok"

    assert fn() == "ok"
    assert len(calls) == 3


def test_budget_is_not_spent_by_a_retry_that_cannot_start(clock: FakeClock) -> None:
    """The delay is counted before it is slept, so no sleep overshoots it."""

    @retry(attempts=10, delay=3.0, max_time=5.0)
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(2, "Time budget of 5s exhausted after 2 attempt(s)"):
        fn()

    assert clock.sleeps == [3.0]
    assert clock.now == pytest.approx(3.0)


def test_attempts_still_bound_the_call(clock: FakeClock) -> None:
    calls: list[int] = []

    @retry(attempts=2, delay=0.1, max_time=60.0)
    def fn() -> NoReturn:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(2, "All 2 attempts failed"):
        fn()

    assert len(calls) == 2
    assert clock.now == pytest.approx(0.1)


def test_budget_applies_without_a_delay(clock: FakeClock) -> None:
    calls: list[int] = []

    @retry(attempts=5, max_time=1.0)
    def fn() -> NoReturn:
        calls.append(1)
        clock.now += 0.6
        msg = "boom"
        raise ValueError(msg)

    with pytest.RaisesGroup(
        ValueError,
        ValueError,
        check=lambda group: "Time budget" in group.message,
    ):
        fn()

    assert len(calls) == 2


def test_return_default_value_after_the_budget(clock: FakeClock) -> None:
    @retry(attempts=10, delay=1.0, max_time=2.0, return_default_value="fallback")
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    assert fn() == "fallback"
    assert clock.now <= 2.0


def test_deadline_flag_and_message(clock: FakeClock) -> None:
    seen: dict[str, object] = {}

    def on_failure(stats: object) -> None:
        attempt = stats.attempt  # type: ignore[attr-defined]
        seen["deadline_reached"] = attempt.deadline_reached
        seen["retry_index"] = attempt.retry_index
        seen["computed_delay"] = attempt.computed_delay
        seen["extra"] = stats.log_extra["deadline_reached"]  # type: ignore[attr-defined]

    @retry(attempts=10, delay=2.0, max_time=3.0, callbacks={"on_failure": on_failure})
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(2, "Time budget of 3s exhausted after 2 attempt(s)"):
        fn()

    assert seen["deadline_reached"] is True
    assert seen["extra"] is True
    assert seen["retry_index"] == 2
    assert clock.sleeps == [2.0]


def test_deadline_is_false_for_an_exhausted_attempts_run(clock: FakeClock) -> None:
    seen: list[bool] = []

    def on_failure(stats: object) -> None:
        seen.append(stats.attempt.deadline_reached)  # type: ignore[attr-defined]

    @retry(attempts=2, delay=0.1, max_time=60.0, callbacks={"on_failure": on_failure})
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(2, "All 2 attempts failed"):
        fn()

    assert seen == [False]
    assert clock.now == pytest.approx(0.1)


def test_success_keeps_the_deadline_flag_false() -> None:
    @retry(attempts=2, delay=0.1, max_time=60.0)
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1


async def test_async_retry_stops_at_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)  # ruff: ignore[shared-clock-mock]
    monkeypatch.setattr(asyncio, "sleep", _async_sleep(fake))  # ruff: ignore[shared-clock-mock]

    calls: list[int] = []

    @retry(attempts=10, delay=1.0, max_time=4.0)
    async def fn() -> None:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(4, "Time budget of 4s exhausted after 4 attempt(s)"):
        await fn()

    assert len(calls) == 4
    assert fake.sleeps == [1.0, 1.0, 1.0]
    assert fake.now <= 4.0


async def test_retry_async_honours_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)  # ruff: ignore[shared-clock-mock]
    monkeypatch.setattr(asyncio, "sleep", _async_sleep(fake))  # ruff: ignore[shared-clock-mock]

    calls: list[int] = []

    @retry_async(attempts=10, delay=1.0, max_time=3.0)
    def blocking() -> None:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(3, "Time budget of 3s exhausted after 3 attempt(s)"):
        await blocking()

    assert len(calls) == 3


def test_budget_can_be_set_globally(clock: FakeClock) -> None:
    config.retry(max_time=2.0)
    calls: list[int] = []

    @retry(attempts=10, delay=1.0)
    def fn() -> NoReturn:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(2, "Time budget of 2s exhausted after 2 attempt(s)"):
        fn()

    assert len(calls) == 2
    assert clock.now <= 2.0


def test_none_disables_a_global_budget() -> None:
    config.retry(max_time=1.0)
    calls: list[int] = []

    @retry(attempts=3, delay=0, max_time=None)
    def fn() -> NoReturn:
        calls.append(1)
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(3, "All 3 attempts failed"):
        fn()

    assert len(calls) == 3


def test_effective_budget_is_readable() -> None:
    retrying = SyncRetrying(attempts=2, max_time=1.5)

    assert retrying.max_time == pytest.approx(1.5)
    assert SyncRetrying(attempts=2).max_time is None
    assert "max_time=1.5" in repr(retrying)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (0, "max_time must be > 0"),
        (-1.0, "max_time must be > 0"),
        (float("nan"), "max_time must be finite"),
        (float("inf"), "max_time must be finite"),
    ],
)
def test_invalid_budget_is_rejected(value: float, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        retry(attempts=2, max_time=value)(lambda: 1)


@pytest.mark.parametrize("value", ["1", True, [], 1 + 0j])
def test_non_numeric_budget_is_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="max_time must be a number of seconds or None"):
        retry(attempts=2, max_time=value)(lambda: 1)  # type: ignore[arg-type]


def test_failure_log_names_the_budget(
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    @retry(attempts=10, max_time=0.001)
    def fn() -> NoReturn:
        clock.now += 0.002
        msg = "boom"
        raise ValueError(msg)

    with _expect_group(1, "Time budget of 0.001s exhausted after 1 attempt(s)"):
        fn()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Time budget exhausted after 1 attempt(s)." in message for message in messages)
