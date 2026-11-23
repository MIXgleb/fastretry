"""Tests for retry lifecycle callbacks."""

import dataclasses as dc
from collections.abc import (
    Callable,
)
from typing import (
    Literal,
    NoReturn,
)
from unittest.mock import (
    MagicMock,
)

import pytest

from fastretry._configs.config import (
    config,
)
from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._utils.callbacks import (
    ResolvedRetryCallbacks,
    RetryCallbacks,
    default_on_failure,
    default_on_retry,
    default_on_success,
    noop_callback,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._utils.logs import (
    Log,
)
from fastretry._utils.stats import (
    AttemptState,
    CallOptions,
    DecoratorOptions,
    GlobalOptions,
    RetryStats,
)

type _STATS_FACTORY_TYPE = Callable[..., RetryStats]
"""Type of the ``stats_factory`` fixture: a ``RetryStats`` builder with keyword defaults."""


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
                traceback_min_level=0,
                install_default_handler=True,
                async_callback_mode="thread_per_call",
                unwrap_single_exception=False,
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


def test_callbacks_all_keys_readonly() -> None:
    assert RetryCallbacks.__readonly_keys__ == frozenset({
        "on_success",
        "on_retry",
        "on_failure",
    })
    assert RetryCallbacks.__mutable_keys__ == frozenset()


def test_falsy_callable_is_not_replaced_by_the_noop() -> None:
    """A callable object may define __len__/__bool__ and be falsy."""
    calls: list[int] = []

    class Collector:
        def __call__(self, stats: object) -> None:
            calls.append(1)

        def __len__(self) -> int:
            return 0

    @retry(attempts=2, delay=0, callbacks={"on_retry": Collector()})  # type: ignore[dict-item]
    def fn() -> NoReturn:
        raise ValueError("boom")

    with pytest.RaisesGroup(ValueError, ValueError):
        fn()

    assert calls == [1, 1]


def test_explicit_none_still_disables_a_callback() -> None:
    calls: list[int] = []

    def on_retry(stats: object) -> None:
        calls.append(1)

    @retry(attempts=2, delay=0, callbacks={"on_retry": on_retry, "on_success": None})
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1
    assert calls == []


def test_falsy_default_callback_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class Collector:
        def __call__(self, stats: object) -> None:
            calls.append(1)

        def __bool__(self) -> bool:
            return False

    config.retry(on_success=Collector())  # type: ignore[arg-type]

    @retry(attempts=1, delay=0)
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1
    assert calls == [1]
