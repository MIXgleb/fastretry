"""Tests for RetryStats and its components."""

import dataclasses as dc

import pytest

from retry._compat.sentinels import (
    UNSET,
)
from retry._utils.logs import (
    LogLevel,
)
from retry._utils.stats import (
    AttemptState,
    CallOptions,
    DecoratorOptions,
    GlobalOptions,
    RetryStats,
)


def _make_stats(attempt: AttemptState, attempts: int = 3) -> RetryStats:
    return RetryStats(
        log=None,
        decorator=DecoratorOptions(
            attempts=attempts,
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
            traceback_min_level=LogLevel.ERROR,
        ),
        call=CallOptions(),
        attempt=attempt,
    )


def test_decorator_fields() -> None:
    opts = DecoratorOptions(
        attempts=3,
        return_default_value=None,
        delay=1.0,
        jitter="none",
        disable_logging=False,
        disable_warnings=False,
        re_raise_exception=True,
        retry_on=(Exception,),
        no_retry_on=(),
        executor=None,
    )
    assert opts.attempts == 3
    assert opts.retry_on == (Exception,)
    assert opts.no_retry_on == ()


def test_decorator_frozen() -> None:
    opts = DecoratorOptions(
        attempts=3,
        return_default_value=None,
        delay=1.0,
        jitter="none",
        disable_logging=False,
        disable_warnings=False,
        re_raise_exception=True,
        retry_on=(Exception,),
        no_retry_on=(),
        executor=None,
    )

    with pytest.raises(dc.FrozenInstanceError):
        opts.attempts = 5


def test_global_fields() -> None:
    opts = GlobalOptions(
        jitter_for_exponential="none",
        jitter_for_fixed="none",
        sync_sleep_call=lambda _: None,
        async_sleep_call=lambda _: None,
        traceback_min_level=LogLevel.ERROR,
    )
    assert opts.traceback_min_level == LogLevel.ERROR


def test_call_defaults() -> None:
    opts = CallOptions()
    assert opts.args == ()
    assert opts.kwargs == {}


def test_call_frozen() -> None:
    opts = CallOptions(args=(1,), kwargs={"a": 1})

    with pytest.raises(dc.FrozenInstanceError):
        opts.args = ()


def test_attempt_defaults() -> None:
    state = AttemptState()
    assert state.fname == ""  # ruff: ignore[compare-to-empty-string]
    assert state.retry_index == 0
    assert state.computed_delay is UNSET
    assert state.result is UNSET
    assert state.last_exception is None
    assert state.exceptions == []
    assert state.retry_aborted is False


@pytest.mark.parametrize(
    ("exc", "expected_in_result"),
    [
        (ValueError("test"), "ValueError: test"),
        (None, "<no exception>"),
        (UNSET, "<no exception>"),
    ],
)
def test_format_exception(
    exc: object,
    expected_in_result: str,
) -> None:
    state = AttemptState()

    if exc is UNSET:
        result = state.format_exception()
    elif exc is None:
        result = state.format_exception(None)
    else:
        state.last_exception = exc
        result = state.format_exception()

    assert expected_in_result in result


def test_attempt_exceptions_with_traceback() -> None:
    state = AttemptState()
    exc = ValueError("test")
    state.exceptions = [exc]
    result = state.exceptions_with_traceback
    assert len(result) == 1
    assert "ValueError: test" in result[0]


def test_log_extra() -> None:
    state = AttemptState(
        fname="test_func",
        retry_index=2,
        started_at=100.0,
        elapsed=1.5,
        computed_delay=0.5,
        last_exception=ValueError("x"),
        retry_aborted=False,
    )
    stats = _make_stats(state)

    extra = stats.log_extra
    assert extra["fname"] == "test_func"
    assert extra["retry_index"] == 2
    assert extra["attempts"] == 3
    assert extra["computed_delay"] == pytest.approx(0.5)
    assert extra["previous_delay"] is None
    assert extra["exception_type"] == "ValueError"
    assert extra["retry_aborted"] is False


def test_log_extra_no_exception() -> None:
    state = AttemptState(fname="f", retry_index=1)
    stats = _make_stats(state, attempts=1)

    assert stats.log_extra["exception_type"] is None


def test_for_call() -> None:
    stats = _make_stats(AttemptState(), attempts=1)

    fresh = stats.for_call(args=(1,), kwargs={"a": 2}, fname="fn", started_at=5.0)
    assert fresh.call.args == (1,)
    assert fresh.call.kwargs == {"a": 2}
    assert fresh.attempt.fname == "fn"
    assert fresh.attempt.started_at == 5

    assert stats.call.args == ()
    assert stats.attempt.fname == ""  # ruff: ignore[compare-to-empty-string]
