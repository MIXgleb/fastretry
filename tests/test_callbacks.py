"""Tests for retry lifecycle callbacks."""

import dataclasses as dc
from collections.abc import (
    Callable,
)
from unittest.mock import (
    MagicMock,
)

import pytest

from retry._utils._callbacks import (
    ResolvedRetryCallbacks,
    RetryCallbacks,
    default_on_failure,
    default_on_retry,
    default_on_success,
    noop_callback,
)
from retry._utils._logs import (
    Log,
)
from retry._utils._stats import (
    AttemptState,
    CallOptions,
    DecoratorOptions,
    GlobalOptions,
    RetryStats,
)
from retry._utils._unset import (
    UNSET,
    UnsetType,
)

type _STATS_FACTORY_TYPE = Callable[..., RetryStats]


@pytest.fixture
def stats_factory() -> _STATS_FACTORY_TYPE:
    def make(
        fname: str = "fn",
        retry_index: int = 1,
        attempts: int = 3,
        result: object = UNSET,
        last_exception: Exception | None = None,
        retry_aborted: bool = False,
        computed_delay: float | UnsetType = UNSET,
    ) -> RetryStats:
        attempt = AttemptState(
            fname=fname,
            retry_index=retry_index,
            result=result,
            last_exception=last_exception,
            retry_aborted=retry_aborted,
            computed_delay=computed_delay,
        )
        log = MagicMock(spec=Log)
        log.record.return_value = True
        return RetryStats(
            log=log,
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
                traceback_min_level=0,
            ),
            call=CallOptions(),
            attempt=attempt,
        )

    return make


def test_typed_dict() -> None:
    cb: RetryCallbacks = {"on_retry": default_on_retry}
    assert cb["on_retry"] is default_on_retry


def test_frozen() -> None:
    r = ResolvedRetryCallbacks(
        on_success=noop_callback,
        on_retry=noop_callback,
        on_failure=noop_callback,
    )

    with pytest.raises(dc.FrozenInstanceError):
        r.on_retry = noop_callback


@pytest.mark.parametrize(
    ("result", "expected_contains"),
    [
        (42, "42"),
        ("hello", "hello"),
        (None, "None"),
        ({"a": 1}, "dict"),
        ([1, 2], "list"),
    ],
)
def test_success_result(
    stats_factory: _STATS_FACTORY_TYPE,
    result: object,
    expected_contains: str,
) -> None:
    stats = stats_factory(result=result)
    default_on_success(stats)
    stats.log.record.assert_called_once()
    call_kwargs = stats.log.record.call_args.kwargs
    assert call_kwargs["log_kind"] == "success"
    assert expected_contains in call_kwargs["message"] % call_kwargs["args"]


def test_success_unset_result(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory(result=UNSET)
    default_on_success(stats)
    call_kwargs = stats.log.record.call_args.kwargs
    assert "UnsetType" in call_kwargs["message"] % call_kwargs["args"]


def test_logs_retry(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory(retry_index=2, attempts=3)
    default_on_retry(stats)
    assert stats.log.record.call_count == 1
    assert stats.log.record.call_args.kwargs["log_kind"] == "retry"


@pytest.mark.parametrize(
    ("computed_delay", "expected_calls"),
    [
        (UNSET, 1),
        (0, 1),
        (-1, 1),
        (1.5, 2),
    ],
)
def test_logs_sleep(
    stats_factory: _STATS_FACTORY_TYPE,
    computed_delay: float | UnsetType,
    expected_calls: int,
) -> None:
    stats = stats_factory(computed_delay=computed_delay)
    default_on_retry(stats)
    assert stats.log.record.call_count == expected_calls


def test_retry_no_exception(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory(last_exception=None)
    default_on_retry(stats)
    assert stats.log.record.call_args.kwargs["last_exception"] is None


@pytest.mark.parametrize(
    ("retry_index", "retry_aborted", "expected_substring"),
    [
        (3, False, "after %d attempts"),
        (1, True, "aborted"),
        (2, True, "not retryable"),
    ],
)
def test_failure_message(
    stats_factory: _STATS_FACTORY_TYPE,
    retry_index: int,
    retry_aborted: bool,
    expected_substring: str,
) -> None:
    stats = stats_factory(retry_index=retry_index, retry_aborted=retry_aborted)
    default_on_failure(stats)
    call_kwargs = stats.log.record.call_args.kwargs
    assert expected_substring in call_kwargs["message"]


def test_failure_args(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory(retry_index=3, attempts=3, retry_aborted=False)
    default_on_failure(stats)
    assert stats.log.record.call_args.kwargs["args"] == (3,)


def test_failure_no_exception(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory(last_exception=None, retry_aborted=False)
    default_on_failure(stats)
    assert stats.log.record.call_args.kwargs["last_exception"] is None


def test_noop(stats_factory: _STATS_FACTORY_TYPE) -> None:
    stats = stats_factory()
    noop_callback(stats)
