"""Tests for runtime introspection."""

import asyncio
import functools
import threading
from collections.abc import (
    Generator,
)
from concurrent.futures import (
    ThreadPoolExecutor,
)
from unittest.mock import (
    MagicMock,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry._utils.introspection import (
    RetryContext,
    _active_runs,
    get_active_runs,
    get_current_run_id,
    get_current_stats,
    get_stats_by_run_id,
    get_stats_for,
    is_retrying,
)
from fastretry._utils.logs import (
    Log,
    LogLevel,
)
from fastretry._utils.stats import (
    AttemptState,
    CallOptions,
    DecoratorOptions,
    GlobalOptions,
    RetryStats,
)


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def _clean_registry() -> Generator[None]:
    _active_runs.clear()
    yield
    _active_runs.clear()


def _make_stats(fname: str = "fn") -> RetryStats:
    return RetryStats(
        log=MagicMock(spec=Log),
        decorator=DecoratorOptions(
            attempts=1,
            max_time=None,
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
            traceback_min_level=LogLevel.ERROR,
            install_default_handler=True,
            async_callback_mode="thread_per_call",
            unwrap_single_exception=False,
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

    with pytest.RaisesGroup(ValueError, ValueError):
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


def test_is_retrying_by_name_and_callable() -> None:
    seen = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        seen.append(is_retrying())
        seen.append(is_retrying(fn))
        seen.append(is_retrying(fn.__qualname__))
        seen.append(bool(get_stats_for(fn)))
        return 1

    assert fn() == 1
    assert seen == [True, True, True, True]
    assert is_retrying(fn) is False
    assert is_retrying(fn.__qualname__) is False
    assert get_stats_for(fn) == {}


def test_is_retrying_unknown_target() -> None:
    assert is_retrying("never_runs") is False
    assert get_stats_for("never_runs") == {}
    assert get_stats_by_run_id(0) is None


def test_callable_without_qualified_name() -> None:
    partial = functools.partial(int)
    opaque = object()

    assert is_retrying(partial) is False
    assert get_stats_for(partial) == {}
    assert is_retrying(opaque) is False
    assert get_stats_for(opaque) == {}


async def test_retrying_inside_async() -> None:
    seen = []

    @retry(attempts=2, delay=0)
    async def fn() -> None:
        seen.append(is_retrying())
        seen.append(get_current_stats() is not None)
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError):
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

    with pytest.RaisesGroup(ValueError):
        await asyncio.gather(a(), b())

    assert all(s is not None and s.attempt.fname.endswith("a") for s in stats_a)
    assert all(s is not None and s.attempt.fname.endswith("b") for s in stats_b)


async def test_get_stats_for_async() -> None:
    run_ids = []

    @retry(attempts=1, delay=0)
    async def fn() -> None:
        run_id = get_current_run_id()
        assert run_id is not None
        run_ids.append(run_id)
        assert is_retrying(fn)
        assert get_stats_for(fn)
        assert get_stats_by_run_id(run_id) is not None
        raise ValueError

    with pytest.RaisesGroup(ValueError):
        await fn()

    assert get_stats_for(fn) == {}
    assert get_stats_by_run_id(run_ids[0]) is None


def test_concurrent_runs_of_same_function() -> None:
    barrier = threading.Barrier(2, timeout=5)
    release = threading.Barrier(2, timeout=5)
    observed = []
    run_ids = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        run_id = get_current_run_id()
        assert run_id is not None
        run_ids.append(run_id)
        barrier.wait()
        observed.append(len(get_stats_for(fn)))
        release.wait()
        return 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(fn) for _ in range(2)]

        assert [future.result() for future in results] == [1, 1]

    assert observed == [2, 2]
    assert len(set(run_ids)) == 2
    assert get_stats_for(fn) == {}


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


def test_snapshot_is_detached_from_live_stats() -> None:
    stats = _make_stats("snap_copy")
    stats.attempt.retry_index = 2
    stats.attempt.attempt_durations.append(0.1)

    snapshot = stats.snapshot()

    stats.attempt.retry_index = 3
    stats.attempt.attempt_durations.append(0.2)

    assert snapshot.attempt is not stats.attempt
    assert snapshot.attempt.retry_index == 2
    assert snapshot.attempt.attempt_durations == [0.1]


def test_registry_returns_live_stats() -> None:
    stats = _make_stats("live_lookup")
    stats.attempt.retry_index = 1

    with RetryContext(stats):
        run_id = get_current_run_id()
        assert run_id is not None

        assert get_stats_for("live_lookup")[run_id] is stats
        assert get_stats_by_run_id(run_id) is stats
        assert get_active_runs()[run_id] is stats

        stats.attempt.retry_index = 2
        assert get_stats_by_run_id(run_id).attempt.retry_index == 2


def test_get_stats_for_partial() -> None:
    seen = []

    @retry(attempts=1, delay=0)
    def fn() -> int:
        partial = functools.partial(fn)
        seen.append(bool(get_stats_for(partial)))
        seen.append(is_retrying(partial))
        return 1

    assert fn() == 1
    assert seen == [True, True]


async def test_get_stats_for_asyncio_task() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @retry(attempts=1, delay=0)
    async def fn() -> int:
        started.set()
        await release.wait()
        return 1

    task = asyncio.create_task(fn())
    await started.wait()

    assert is_retrying(task)
    found = get_stats_for(task)
    assert len(found) == 1
    assert next(iter(found.values())).attempt.fname == fn.__qualname__

    release.set()
    assert await task == 1


def test_get_active_runs() -> None:
    assert get_active_runs() == {}

    stats = _make_stats("active")

    with RetryContext(stats):
        assert list(get_active_runs().values()) == [stats]

    assert get_active_runs() == {}


def test_retry_context_unregisters_on_exception() -> None:
    def _boom() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    stats = _make_stats("boom")

    with pytest.raises(RuntimeError, match="boom"), RetryContext(stats):
        _boom()

    assert get_stats_for("boom") == {}
    assert get_current_stats() is None
    assert is_retrying() is False


def test_run_ids_are_unique() -> None:
    ids = []

    with RetryContext(_make_stats("first")):
        ids.append(get_current_run_id())

    with RetryContext(_make_stats("second")):
        ids.append(get_current_run_id())

    assert None not in ids
    assert len(set(ids)) == 2


def test_stats_reflect_current_attempt() -> None:
    seen = []

    @retry(attempts=3, delay=0)
    def fn() -> int:
        stats = get_current_stats()
        assert stats is not None
        seen.append(stats.attempt.retry_index)
        if stats.attempt.retry_index < 3:
            raise ValueError
        return 1

    assert fn() == 1
    assert seen == [1, 2, 3]


def test_introspection_in_callback_and_delay() -> None:
    seen = []

    def on_retry(stats: RetryStats) -> None:
        seen.append((is_retrying(), get_current_stats() is stats))

    @retry(attempts=2, delay=0.01, callbacks={"on_retry": on_retry})
    def fn() -> int:
        stats = get_current_stats()
        assert stats is not None
        if stats.attempt.retry_index == 1:
            raise ValueError
        return 1

    assert fn() == 1
    assert seen == [(True, True)]
    assert is_retrying() is False


async def test_introspection_inside_executor() -> None:
    seen = []

    @retry_async(attempts=1)
    def blocking() -> int:
        seen.append(is_retrying())
        seen.append(get_current_stats() is not None)
        return 1

    assert await blocking() == 1
    assert seen == [True, True]
    assert is_retrying() is False


async def test_stats_visible_from_another_task() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    run_ids = []

    @retry(attempts=1, delay=0)
    async def fn() -> int:
        run_id = get_current_run_id()
        assert run_id is not None
        run_ids.append(run_id)
        started.set()
        await release.wait()
        return 1

    async def observer() -> None:
        await started.wait()
        stats = get_stats_by_run_id(run_ids[0])
        assert stats is not None
        assert stats.attempt.fname == fn.__qualname__
        assert is_retrying(fn)
        release.set()

    await asyncio.gather(fn(), observer())

    assert get_stats_by_run_id(run_ids[0]) is None
    assert get_stats_for(fn) == {}
