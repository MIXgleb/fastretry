"""Edge cases and corner cases."""

import asyncio
from typing import (
    Literal,
    NoReturn,
)

import pytest

from retry._retry import (
    retry,
)


def test_zero_attempts() -> None:
    with pytest.warns(UserWarning, match="must be >= 1"):

        @retry(attempts=0, delay=0)
        def fn() -> Literal[1]:
            return 1

    assert fn() == 1


def test_return_none_as_default() -> None:
    with pytest.warns(
        expected_warning=UserWarning,
        match="return_default_value None does not match the declared return type",
    ):

        @retry(attempts=1, delay=0, return_default_value=None)
        def fn() -> NoReturn:
            raise ValueError

    assert fn() is None


def test_exception_group_from_single_exc() -> None:
    @retry(attempts=1, delay=0)
    def fn() -> NoReturn:
        msg = "x"
        raise ValueError(msg)

    with pytest.raises(ExceptionGroup) as eg:
        fn()
    assert len(eg.value.exceptions) == 1

    # BaseExceptionGroup resolves to ExceptionGroup
    assert isinstance(eg.value, ExceptionGroup)


def test_keyboard_interrupt_not_retried() -> None:
    calls: list[int] = []

    @retry(attempts=5, delay=0)
    def fn() -> NoReturn:
        calls.append(1)
        raise KeyboardInterrupt

    with pytest.raises(BaseExceptionGroup):
        fn()

    assert len(calls) == 1


async def test_cancelled_error_not_retried() -> None:
    calls: list[int] = []

    @retry(attempts=5, delay=0)
    async def fn() -> NoReturn:
        calls.append(1)
        raise asyncio.CancelledError

    with pytest.raises(BaseExceptionGroup):
        await fn()

    assert len(calls) == 1


def test_retry_bare_decorator() -> None:
    @retry
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1


def test_retry_callable_explicit() -> None:
    def fn() -> Literal[1]:
        return 1

    wrapped = retry(fn)
    assert wrapped() == 1
