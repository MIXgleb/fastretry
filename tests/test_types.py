"""Tests for TypedDict definitions."""

from typing import (
    get_type_hints,
)

from fastretry._compat.nodes import (
    is_typeddict,
)
from fastretry._types import (
    DefaultsKwargs,
    LoggingDefaultsKwargs,
    RetryDefaultsKwargs,
    RetryKwargs,
    RetryWithExecutorKwargs,
    _LoggingDefaultOptions,
    _RetryDefaultOptions,
    _RetryOptions,
)


def test_retry_options_is_typeddict() -> None:
    assert is_typeddict(_RetryOptions)


def test_retry_kwargs_is_typeddict() -> None:
    assert is_typeddict(RetryKwargs)


def test_retry_defaults_kwargs_is_typeddict() -> None:
    assert is_typeddict(RetryDefaultsKwargs)


def test_logging_kwargs_is_typeddict() -> None:
    assert is_typeddict(LoggingDefaultsKwargs)


def test_defaults_kwargs_is_typeddict() -> None:
    assert is_typeddict(DefaultsKwargs)


def test_retry_kwargs_inherits_options() -> None:
    d = get_type_hints(RetryKwargs)

    assert "attempts" in d
    assert "return_default_value" in d
    assert "delay" in d
    assert "jitter" in d
    assert "disable_logging" in d
    assert "disable_warnings" in d
    assert "retry_on" in d
    assert "no_retry_on" in d
    assert "callbacks" in d


def test_retry_with_executor_kwargs_inherits_options() -> None:
    d = get_type_hints(RetryWithExecutorKwargs)

    assert "attempts" in d
    assert "return_default_value" in d
    assert "delay" in d
    assert "jitter" in d
    assert "disable_logging" in d
    assert "disable_warnings" in d
    assert "retry_on" in d
    assert "no_retry_on" in d
    assert "callbacks" in d
    assert "executor" in d


def test_retry_defaults_kwargs_keys() -> None:
    d = get_type_hints(RetryDefaultsKwargs)

    assert "attempts" in d
    assert "delay" in d
    assert "disable_logging" in d
    assert "disable_warnings" in d
    assert "retry_on" in d
    assert "no_retry_on" in d
    assert "on_success" in d
    assert "on_retry" in d
    assert "on_failure" in d
    assert "jitter_for_exponential" in d
    assert "jitter_for_fixed" in d
    assert "sync_sleep_call" in d
    assert "async_sleep_call" in d


def test_logging_kwargs_keys() -> None:
    d = get_type_hints(LoggingDefaultsKwargs)

    assert "level_success" in d
    assert "level_retry" in d
    assert "level_failure" in d
    assert "level_sleep" in d
    assert "traceback_min_level" in d


def test_defaults_kwargs_combines() -> None:
    d = get_type_hints(DefaultsKwargs)

    assert "attempts" in d
    assert "delay" in d
    assert "disable_logging" in d
    assert "disable_warnings" in d
    assert "retry_on" in d
    assert "no_retry_on" in d
    assert "on_success" in d
    assert "on_retry" in d
    assert "on_failure" in d
    assert "jitter_for_exponential" in d
    assert "jitter_for_fixed" in d
    assert "sync_sleep_call" in d
    assert "async_sleep_call" in d
    assert "level_success" in d
    assert "level_retry" in d
    assert "level_failure" in d
    assert "level_sleep" in d
    assert "traceback_min_level" in d


def test_retry_options_all_keys_readonly() -> None:
    assert _RetryOptions.__readonly_keys__ == frozenset({
        "attempts",
        "return_default_value",
        "delay",
        "jitter",
        "disable_logging",
        "disable_warnings",
        "retry_on",
        "no_retry_on",
        "callbacks",
    })
    assert _RetryOptions.__mutable_keys__ == frozenset()


def test_retry_default_options_all_keys_readonly() -> None:
    assert _RetryDefaultOptions.__readonly_keys__ == frozenset({
        "attempts",
        "delay",
        "disable_logging",
        "disable_warnings",
        "retry_on",
        "no_retry_on",
        "on_success",
        "on_retry",
        "on_failure",
        "jitter_for_exponential",
        "jitter_for_fixed",
        "sync_sleep_call",
        "async_sleep_call",
    })
    assert _RetryDefaultOptions.__mutable_keys__ == frozenset()


def test_logging_default_options_all_keys_readonly() -> None:
    assert _LoggingDefaultOptions.__readonly_keys__ == frozenset({
        "level_success",
        "level_retry",
        "level_failure",
        "level_sleep",
        "traceback_min_level",
    })
    assert _LoggingDefaultOptions.__mutable_keys__ == frozenset()
