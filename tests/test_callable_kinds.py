"""The retrying strategy must follow what calling the callable returns.

``inspect.iscoroutinefunction`` is False for an instance whose ``__call__`` is
async, so such a callable took the sync path: the wrapper returned the
coroutine object without awaiting it, no attempt was retried and the exception
escaped un-wrapped.
"""

import asyncio
from typing import (
    Literal,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)


class FlakyJob:
    """Async callable that fails ``failures`` times before succeeding."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def __call__(self, value: int = 1) -> int:
        self.calls += 1

        if self.calls <= self.failures:
            msg = "try again"
            raise ValueError(msg)

        return value * 2


class SyncJob:
    """Sync callable that fails once before succeeding."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Literal["ok"]:
        self.calls += 1

        if self.calls == 1:
            msg = "try again"
            raise ValueError(msg)

        return "ok"


def test_async_callable_object_is_retried_by_retry() -> None:
    job = FlakyJob(failures=2)
    wrapped = retry(attempts=3, delay=0)(job)

    async def run() -> int:
        return await wrapped(21)

    assert asyncio.run(run()) == 42
    assert job.calls == 3


def test_async_callable_object_is_awaited_by_retry_async() -> None:
    job = FlakyJob(failures=1)
    wrapped = retry_async(attempts=2, delay=0)(job)

    async def run() -> int:
        return await wrapped(10)

    assert asyncio.run(run()) == 20
    assert job.calls == 2


def test_async_callable_object_failure_is_grouped() -> None:
    job = FlakyJob(failures=99)
    wrapped = retry(attempts=2, delay=0)(job)

    async def run() -> None:
        await wrapped()

    with pytest.raises(ExceptionGroup):
        asyncio.run(run())

    assert job.calls == 2


def test_sync_callable_object_is_still_synchronous() -> None:
    job = SyncJob()
    wrapped = retry(attempts=2, delay=0)(job)

    assert not asyncio.iscoroutine(wrapped())
    assert job.calls == 2


def test_class_object_is_not_treated_as_a_coroutine_function() -> None:
    class Plain:
        def __init__(self, value: int = 1) -> None:
            self.value = value

    built = retry(attempts=1, delay=0)(Plain)

    instance = built(7)

    assert not asyncio.iscoroutine(instance)
    assert isinstance(instance, Plain)
    assert instance.value == 7
