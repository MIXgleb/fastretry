"""Tests for the shared background loop used by async callbacks."""

import asyncio
import concurrent.futures
import os
import threading
from collections.abc import (
    Generator,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

from fastretry._utils import (
    shared_loop as shared_loop_module,
)
from fastretry._utils.shared_loop import (
    SharedLoop,
)


@pytest.fixture
def loop() -> Generator[SharedLoop]:
    """
    Provide a private shared loop and shut it down afterwards.

    Yields
    ------
    SharedLoop
        Fresh, not yet started loop instance.

    """
    instance = SharedLoop()
    yield instance
    instance.shutdown()


def test_is_owner_thread_is_false_outside(loop: SharedLoop) -> None:
    assert loop.is_owner_thread() is False


def test_run_callback_executes_on_loop_thread(loop: SharedLoop) -> None:
    seen: list[str] = []
    owner: list[bool] = []

    async def cb() -> None:
        seen.append(threading.current_thread().name)
        owner.append(loop.is_owner_thread())

    loop.run_callback(cb())

    assert seen == ["fastretry-callback-loop"]
    assert owner == [True]


def test_run_callback_reraises_callback_exception(loop: SharedLoop) -> None:
    async def boom() -> None:
        msg = "callback failed"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="callback failed"):
        loop.run_callback(boom())

    done: list[int] = []

    async def ok() -> None:
        done.append(1)

    loop.run_callback(ok())

    assert done == [1]


def test_run_callback_keeps_loop_alive_after_base_exception(loop: SharedLoop) -> None:
    async def stop() -> None:
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        loop.run_callback(stop())

    done: list[int] = []

    async def ok() -> None:
        done.append(1)

    loop.run_callback(ok())

    assert done == [1]


def test_run_callback_waits_for_slow_callback(loop: SharedLoop, mocker: MockerFixture) -> None:
    _ = mocker.patch.object(shared_loop_module, "_WAIT_SLICE", 0.01)
    done: list[int] = []

    async def slow() -> None:
        await asyncio.sleep(0.05)
        done.append(1)

    loop.run_callback(slow())

    assert done == [1]


def test_wait_raises_when_loop_is_unhealthy(loop: SharedLoop, mocker: MockerFixture) -> None:
    _ = mocker.patch.object(shared_loop_module, "_WAIT_SLICE", 0.01)
    future: concurrent.futures.Future[None] = concurrent.futures.Future()
    idle_loop = asyncio.new_event_loop()
    coro = asyncio.sleep(0)

    try:
        with pytest.raises(RuntimeError, match="shared callback event loop stopped"):
            loop._wait(future, loop=idle_loop, coro=coro)
    finally:
        idle_loop.close()

    assert coro.cr_frame is None


def test_ensure_loop_reuses_healthy_loop(loop: SharedLoop) -> None:
    first = loop._ensure_loop()
    second = loop._ensure_loop()

    assert first is second


def test_ensure_loop_starts_new_loop_after_fork(loop: SharedLoop) -> None:
    loop._pid = os.getpid() + 1

    created = loop._ensure_loop()

    assert created.is_running() is True
    assert loop._pid == os.getpid()


def test_ensure_loop_rechecks_inside_lock(loop: SharedLoop, mocker: MockerFixture) -> None:
    created = loop._ensure_loop()
    _ = mocker.patch.object(SharedLoop, "_is_healthy", side_effect=[False, True])

    reused = loop._ensure_loop()

    assert reused is created


def test_ensure_loop_starts_new_loop_when_still_unhealthy(
    loop: SharedLoop,
    mocker: MockerFixture,
) -> None:
    _ = mocker.patch.object(SharedLoop, "_is_healthy", return_value=False)

    created = loop._ensure_loop()

    assert created.is_running() is True


def test_is_healthy_requires_live_thread(loop: SharedLoop) -> None:
    asyncio_loop = asyncio.new_event_loop()
    finished = threading.Thread(target=lambda: None)
    finished.start()
    finished.join()

    loop._loop = asyncio_loop
    loop._thread = finished
    loop._pid = os.getpid()

    try:
        assert loop._is_healthy(asyncio_loop) is False
    finally:
        asyncio_loop.close()


def test_is_healthy_requires_alive_thread(loop: SharedLoop) -> None:
    asyncio_loop = loop._ensure_loop()
    loop._thread = None

    assert loop._is_healthy(asyncio_loop) is False


def test_is_healthy_requires_running_loop(loop: SharedLoop, mocker: MockerFixture) -> None:
    asyncio_loop = loop._ensure_loop()
    _ = mocker.patch.object(asyncio_loop, "is_running", return_value=False)

    assert loop._is_healthy(asyncio_loop) is False


def test_is_healthy_requires_same_process(loop: SharedLoop, mocker: MockerFixture) -> None:
    asyncio_loop = loop._ensure_loop()
    _ = mocker.patch.object(shared_loop_module.os, "getpid", return_value=-1)

    assert loop._is_healthy(asyncio_loop) is False


def test_shutdown_without_start_is_noop() -> None:
    instance = SharedLoop()

    instance.shutdown()

    assert instance._loop is None


def test_shutdown_stops_loop_and_allows_restart(loop: SharedLoop) -> None:
    first = loop._ensure_loop()

    loop.shutdown()

    assert first.is_closed() is True
    assert loop._loop is None

    second = loop._ensure_loop()

    assert second is not first
    assert second.is_running() is True


def test_shutdown_with_stopped_loop_skips_stop_call() -> None:
    instance = SharedLoop()
    finished = threading.Thread(target=lambda: None)
    finished.start()
    finished.join()
    idle_loop = asyncio.new_event_loop()

    instance._loop = idle_loop
    instance._thread = finished

    try:
        instance.shutdown()
    finally:
        idle_loop.close()

    assert instance._thread is None


def test_loop_stopped_while_the_callback_runs_reports_runtime_error() -> None:
    """Closing an executing coroutine raises ValueError and hides the error."""
    loop = SharedLoop()
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    async def callback() -> None:
        started.set()
        release.wait(2.0)

    def caller() -> None:
        try:
            loop.run_callback(callback())
        except BaseException as exc:  # ruff: ignore[blind-except]
            errors.append(exc)

    thread = threading.Thread(target=caller)
    thread.start()

    try:
        assert started.wait(2.0)
        loop.shutdown()
        thread.join(10.0)
    finally:
        release.set()

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "stopped before the callback completed" in str(errors[0])
