"""Tests for runtime introspection."""

import asyncio
import sys
import threading

import pytest
from fastretry._introspection import (
    RetryContext,
    _active_runs,
    _lock,
)

from fastretry import (
    get_current_run_id,
    get_current_stats,
    get_stats_by_run_id,
    get_stats_for,
    is_retrying,
    retry,
)
from fastretry._utils.stats import (
    AttemptState,
    CallOptions,
    DecoratorOptions,
    GlobalOptions,
    RetryStats,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    _active_runs.clear()
    yield
    _active_runs.clear()


def _make_stats(fname: str = "fn") -> RetryStats:
    return RetryStats(
        log=None,  # type: ignore[arg-type]
        decorator=DecoratorOptions(
            attempts=1,
            return_default_value=None,
            delay=0.0,
            jitter="none",
            disable_logging=False,
            disable_warnings=False,
            re_raise_exception=True,
            retry_on=(Exception,),
            no_retry_on=(),
            executor=None,
        ),
        global_options=GlobalOptions(
            jitter_for_exponential="none",
            jitter_for_fixed="none",
            sync_sleep_call=lambda _: None,
            async_sleep_call=lambda _: None,
            traceback_min_level=0,
        ),
        call=CallOptions(),
        attempt=AttemptState(fname=fname),
    )


def test_not_retrying_outside() -> None:
    assert is_retrying() is False
    assert get_current_stats() is None
    assert get_current_run_id() is None


def test_retrying_inside_sync() -> None:
    seen = []

    @retry(attempts=2, delay=0)
    def fn() -> None:
        seen.append(is_retrying())
        seen.append(get_current_stats() is not None)
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(ExceptionGroup):
        fn()

    assert seen == [True, True, True, True]


def test_stats_reset_after_success() -> None:
    @retry(attempts=1, delay=0)
    def fn() -> int:
        return 1

    assert fn() == 1
    assert is_retrying() is False
    assert get_current_stats() is None
    assert get_current_run_id() is None


def test_run_id_inside_and_after() -> None:
    captured = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        captured.append(get_current_run_id())
        return 1

    _ = fn()
    assert len(captured) == 1
    assert captured[0] is not None
    assert get_stats_by_run_id(captured[0]) is None


def test_is_retrying_by_name_sync() -> None:
    seen = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        seen.append(is_retrying("fn"))
        return 1

    _ = fn()
    assert seen == [True]
    assert is_retrying("fn") is False


async def test_retrying_inside_async() -> None:
    seen = []

    @retry(attempts=2, delay=0)
    async def fn() -> None:
        seen.append(is_retrying())
        seen.append(get_current_stats() is not None)
        raise ValueError

    with pytest.raises(ExceptionGroup):
        await fn()

    assert seen == [True, True, True, True]


async def test_isolation_between_tasks() -> None:
    stats_a = []
    stats_b = []

    @retry(attempts=1, delay=0)
    async def a() -> None:
        stats_a.append(get_current_stats())
        raise ValueError

    @retry(attempts=1, delay=0)
    async def b() -> None:
        stats_b.append(get_current_stats())
        raise ValueError

    with pytest.raises(ExceptionGroup):
        await asyncio.gather(a(), b())

    assert all(s is not None and s.attempt.fname.endswith("a") for s in stats_a)
    assert all(s is not None and s.attempt.fname.endswith("b") for s in stats_b)


async def test_get_stats_for_async() -> None:
    run_ids = []

    @retry(attempts=1, delay=0)
    async def fn() -> None:
        run_id = get_current_run_id()
        run_ids.append(run_id)
        assert is_retrying("fn")
        assert get_stats_for("fn")
        assert get_stats_by_run_id(run_id) is not None  # type: ignore[arg-type]
        raise ValueError

    with pytest.raises(ExceptionGroup):
        await fn()

    assert get_stats_for("fn") == {}
    assert get_stats_by_run_id(run_ids[0]) is None  # type: ignore[arg-type]


def test_multiple_concurrent_runs_same_name() -> None:
    run_ids = []

    @retry(attempts=1, delay=0)
    def fn() -> None:
        run_ids.append(get_current_run_id())
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    # Both runs finished, registry cleaned.
    assert len(run_ids) == 1
    assert get_stats_for("fn") == {}


def test_retry_context_registers_and_unregisters() -> None:
    stats = _make_stats("ctx_fn")
    assert get_stats_for("ctx_fn") == {}

    with RetryContext(stats):
        assert get_stats_for("ctx_fn")
        assert get_current_stats() is stats
        assert is_retrying() is True

    assert get_stats_for("ctx_fn") == {}
    assert get_current_stats() is None


def test_retry_context_restores_nested_stats() -> None:
    outer = _make_stats("outer")
    inner = _make_stats("inner")

    with RetryContext(outer):
        assert get_current_stats() is outer
        with RetryContext(inner):
            assert get_current_stats() is inner
        assert get_current_stats() is outer

    assert get_current_stats() is None


def test_sync_in_thread() -> None:
    seen = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        seen.append(is_retrying())
        seen.append(get_current_stats() is not None)
        return 1

    thread = threading.Thread(target=fn)
    thread.start()
    thread.join()

    assert seen == [True, True]
    assert is_retrying() is False


def test_get_stats_for_snapshot() -> None:
    stats_a = _make_stats("snap")
    stats_b = _make_stats("snap")

    with RetryContext(stats_a):
        snapshot = get_stats_for("snap")
        assert len(snapshot) == 1
        with RetryContext(stats_b):
            assert len(get_stats_for("snap")) == 2
        # snapshot is not affected by later registrations
        assert len(snapshot) == 1


def test_lock_is_context_manager() -> None:
    with _lock:
        pass  # should not raise


@pytest.mark.skipif(
    not hasattr(sys, "_is_gil_enabled") or sys._is_gil_enabled(),
    reason="Requires free-threaded Python",
)
def test_free_threaded_registry() -> None: ...
