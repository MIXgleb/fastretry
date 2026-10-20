"""Tests for BaseRetrying internals."""

from typing import (
    NoReturn,
)

import pytest

from fastretry._compat.sentinels import (
    UNSET,
)
from fastretry._config import (
    config,
)
from fastretry._retry import (
    retry,
)
from fastretry._utils.callbacks import (
    default_on_failure,
    default_on_retry,
    default_on_success,
    noop_callback,
)
from fastretry._utils.delay import (
    ExponentialDelay,
)
from fastretry._utils.logs import (
    LogLevel,
)
from fastretry._utils.stats import (
    RetryStats,
)
from fastretry.base import (
    BaseRetrying,
)
from fastretry.sync_retry import (
    SyncRetrying,
)


def test_init_subclass_requires_wrapper_kind() -> None:
    with pytest.raises(TypeError, match="must define wrapper_kind"):

        class _Bad(BaseRetrying):
            pass


def test_copy() -> None:
    original = SyncRetrying(attempts=3)
    copy = original.copy()
    assert copy is not original
    assert copy.attempts == 3


def test_resolve_callbacks_unset() -> None:
    r = SyncRetrying(callbacks=UNSET)
    assert r.callbacks.on_success is default_on_success
    assert r.callbacks.on_retry is default_on_retry
    assert r.callbacks.on_failure is default_on_failure


def test_resolve_callbacks_none() -> None:
    r = SyncRetrying(callbacks=None)
    assert r.callbacks.on_success is noop_callback
    assert r.callbacks.on_retry is noop_callback
    assert r.callbacks.on_failure is noop_callback


def test_resolve_callbacks_partial() -> None:
    def cb(_: RetryStats) -> None:
        return None

    r = SyncRetrying(callbacks={"on_retry": cb})
    assert cb(None) is None
    assert r.callbacks.on_retry is cb
    assert r.callbacks.on_success is default_on_success
    assert r.callbacks.on_failure is default_on_failure


def test_resolve_callbacks_explicit_none() -> None:
    r = SyncRetrying(callbacks={"on_retry": None})
    assert r.callbacks.on_retry is noop_callback
    assert r.callbacks.on_success is default_on_success


def test_resolve_callbacks_global_none() -> None:
    config.retry(on_retry=None)
    r = SyncRetrying(callbacks=UNSET)
    assert r.callbacks.on_retry is noop_callback


def test_validate_attempts_below_one() -> None:
    with pytest.warns(UserWarning, match="must be >= 1"):
        r = SyncRetrying(attempts=0)

    assert r.attempts == 1


def test_validate_delay_negative() -> None:
    with pytest.warns(UserWarning, match="must be >= 0"):
        r = SyncRetrying(delay=-1)

    assert r.delay == 0


@pytest.mark.parametrize(
    ("delay", "match"),
    [
        (ExponentialDelay(delay=-1), "delay must be > 0"),
        (ExponentialDelay(delay=1, backoff_factor=0), "backoff factor must be > 0"),
        (ExponentialDelay(delay=1, max_delay=0), "maximum delay must be > 0"),
        (ExponentialDelay(delay=10, max_delay=5), "must be >= base delay"),
    ],
)
def test_validate_exponential_delay(delay: ExponentialDelay, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _ = SyncRetrying(delay=delay)


def test_validate_exponential_max_delay_valid() -> None:
    r = SyncRetrying(delay=ExponentialDelay(delay=1, max_delay=5))
    assert r.delay.max_delay == 5


def test_derive_jitter_explicit() -> None:
    r = SyncRetrying(delay=1, jitter="full")
    assert r.jitter == "full"


def test_derive_jitter_from_exponential_default() -> None:
    config.retry(jitter_for_exponential="equal")
    r = SyncRetrying(delay=ExponentialDelay(delay=1))
    assert r.jitter == "equal"


def test_derive_jitter_from_fixed_default() -> None:
    config.retry(jitter_for_fixed="full")
    r = SyncRetrying(delay=1)
    assert r.jitter == "full"


def test_prepare_retry_aborted_no_retry_on() -> None:
    captured = []

    @retry(attempts=5, delay=0, no_retry_on=ValueError, callbacks={"on_failure": captured.append})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    assert captured[0].attempt.retry_aborted is True


def test_prepare_retry_aborted_not_in_retry_on() -> None:
    captured = []

    @retry(attempts=5, delay=0, retry_on=ValueError, callbacks={"on_failure": captured.append})
    def fn() -> NoReturn:
        raise TypeError

    with pytest.raises(ExceptionGroup):
        fn()

    assert captured[0].attempt.retry_aborted is True


def test_prepare_retry_exhausted() -> None:
    captured = []

    @retry(attempts=2, delay=0, callbacks={"on_failure": captured.append})
    def fn() -> NoReturn:
        raise ValueError

    with pytest.raises(ExceptionGroup):
        fn()

    assert captured[0].attempt.retry_aborted is False


def test_repr() -> None:
    r = SyncRetrying(attempts=3)
    text = repr(r)
    assert "SyncRetrying" in text
    assert "attempts=3" in text


def test_abstract_wrap_raises() -> None:
    class _Concrete(BaseRetrying):
        wrapper_kind = "test"

        def _wrap(self, func):  # ruff: ignore[missing-return-type-private-function, missing-type-function-argument, no-self-use]
            return func

        def _sleep(self, *, stats) -> None:  # ruff: ignore[missing-type-function-argument, no-self-use, unused-method-argument]
            return None

        def _call_callback(self, *, callback, stats):  # ruff: ignore[missing-return-type-private-function, missing-type-function-argument, no-self-use]
            return callback(stats)

        def _safe_call_callback(self, *, callback, stats):  # ruff: ignore[missing-return-type-private-function, missing-type-function-argument, no-self-use]
            return callback(stats)

    assert _Concrete()._wrap(lambda: None)() is None
    assert _Concrete()._sleep(stats=None) is None
    assert _Concrete()._call_callback(callback=lambda x: x, stats=None) is None
    assert _Concrete()._safe_call_callback(callback=lambda x: x, stats=None) is None

    instance = _Concrete()

    with pytest.raises(NotImplementedError):
        BaseRetrying._wrap(instance, lambda: None)
    with pytest.raises(NotImplementedError):
        BaseRetrying._sleep(instance, stats=None)
    with pytest.raises(NotImplementedError):
        BaseRetrying._call_callback(instance, callback=lambda _: None, stats=None)
    with pytest.raises(NotImplementedError):
        BaseRetrying._safe_call_callback(instance, callback=lambda _: None, stats=None)


def test_disabled_log_swallowed() -> None:
    config.logging(level_failure=LogLevel.OFF)

    with pytest.warns(UserWarning, match="Logging is disabled or the 'failure' log level is OFF"):
        SyncRetrying()._log_swallowed(operation="test call", exc=AssertionError, extra={})


def test_log_swallowed_falls_back_to_warning() -> None:
    r = SyncRetrying(
        disable_warnings=False,
        disable_logging=True,
    )

    with pytest.warns(UserWarning, match="Logging is disabled or the 'failure' log level is OFF"):
        r._log_swallowed(operation="test", exc=ValueError("x"), extra={})


def test_validate_return_type_is_false() -> None:

    with pytest.warns(expected_warning=UserWarning, match="Type mismatch for"):

        @retry(return_default_value=None)
        def fn() -> int:
            return 1

    r = fn()
    assert r == 1


def test_validate_return_type_is_true() -> None:
    @retry(return_default_value=123)
    def fn() -> int:
        return 1

    r = fn()
    assert r == 1


def test_validate_return_type_is_none() -> None:
    @retry(return_default_value="result")
    def fn() -> object:
        return 1

    r = fn()
    assert r == 1
