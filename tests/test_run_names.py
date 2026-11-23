"""A live run must be findable by every target the lookups accept.

The retry wrappers record the call name, and the introspection lookups resolve
the target they are given, so both sides share one resolver. A decorated
:class:`functools.partial` or an instance of a callable class used to be
recorded as ``<anonymous>`` and could not be found at all.
"""

import asyncio
import functools
from typing import (
    Literal,
    NoReturn,
)

from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry.introspection import (
    get_active_runs,
    get_current_stats,
    get_stats_for,
    is_retrying,
)


def test_partial_run_is_findable() -> None:
    seen: dict[str, object] = {}

    def body() -> str:
        current = get_current_stats()
        assert current is not None
        seen["fname"] = current.attempt.fname
        seen["by_wrapper"] = is_retrying(wrapped)
        seen["by_partial"] = is_retrying(part)
        seen["stats_by_wrapper"] = len(get_stats_for(wrapped))
        seen["stats_by_partial"] = len(get_stats_for(part))
        return "ok"

    part = functools.partial(body)
    wrapped = retry(attempts=1, delay=0)(part)

    assert wrapped() == "ok"
    assert seen == {
        "fname": "test_partial_run_is_findable.<locals>.body",
        "by_wrapper": True,
        "by_partial": True,
        "stats_by_wrapper": 1,
        "stats_by_partial": 1,
    }
    assert get_active_runs() == {}


def test_callable_instance_run_is_findable() -> None:
    seen: dict[str, object] = {}

    class Job:
        def __call__(self) -> str:
            current = get_current_stats()
            assert current is not None
            seen["fname"] = current.attempt.fname
            seen["by_instance"] = is_retrying(job)
            seen["active"] = len(get_active_runs())
            return "done"

    job = Job()
    wrapped = retry(attempts=1, delay=0)(job)

    assert wrapped() == "done"
    assert seen == {"fname": "<anonymous>", "by_instance": True, "active": 1}


def test_bound_method_run_keeps_its_qualified_name() -> None:
    class Client:
        def __init__(self) -> None:
            self.names: list[str] = []

        @retry(attempts=1, delay=0)
        def fetch(self) -> Literal["ok"]:
            current = get_current_stats()
            assert current is not None
            self.names.append(current.attempt.fname)
            return "ok"

    client = Client()
    assert client.fetch() == "ok"
    assert client.names == ["test_bound_method_run_keeps_its_qualified_name.<locals>.Client.fetch"]


def test_plain_function_run_is_findable() -> None:
    seen: list[int] = []

    @retry(attempts=2, delay=0)
    def fn() -> NoReturn:
        seen.append(len(get_stats_for(fn)))
        raise ValueError("boom")

    try:
        fn()
    except BaseException:
        pass

    assert seen == [1, 1]


def test_partial_of_an_async_function_is_findable() -> None:
    seen: dict[str, object] = {}

    async def body(value: int) -> int:
        current = get_current_stats()
        assert current is not None
        seen["fname"] = current.attempt.fname
        seen["by_partial"] = is_retrying(part)
        return value * 2

    part = functools.partial(body, 21)
    wrapped = retry(attempts=1, delay=0)(part)

    async def run() -> int:
        return await wrapped()

    assert asyncio.run(run()) == 42
    assert seen == {
        "fname": "test_partial_of_an_async_function_is_findable.<locals>.body",
        "by_partial": True,
    }


def test_task_target_resolves_to_the_wrapped_coroutine() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @retry(attempts=1, delay=0)
    async def fn() -> Literal["ok"]:
        started.set()
        await release.wait()
        return "ok"

    async def run() -> None:
        task = asyncio.create_task(fn())
        await started.wait()
        seen["by_task"] = is_retrying(task)
        seen["stats"] = len(get_stats_for(task))
        release.set()
        assert await task == "ok"

    seen: dict[str, object] = {}
    asyncio.run(run())
    assert seen == {"by_task": True, "stats": 1}


def test_retry_async_run_is_findable() -> None:
    seen: dict[str, object] = {}

    @retry_async(attempts=1, delay=0)
    def blocking() -> Literal["ok"]:
        current = get_current_stats()
        assert current is not None
        seen["fname"] = current.attempt.fname
        seen["by_self"] = is_retrying(blocking)
        return "ok"

    async def run() -> str:
        return await blocking()

    assert asyncio.run(run()) == "ok"
    assert seen == {
        "fname": "test_retry_async_run_is_findable.<locals>.blocking",
        "by_self": True,
    }
