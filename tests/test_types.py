"""Tests for TypedDict definitions."""

from typing import (
    get_type_hints,
)

from retry._compat.nodes import (
    is_typeddict,
)
from retry._types import (
    DefaultsKwargs,
    LoggingDefaultsKwargs,
    RetryDefaultsKwargs,
    RetryKwargs,
    RetryWithExecutorKwargs,
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
    assert get_type_hints(RetryKwargs) == {}


def test_retry_with_executor_kwargs_inherits_options() -> None:
    assert get_type_hints(RetryWithExecutorKwargs) == {}


def test_retry_defaults_kwargs_keys() -> None:
    assert get_type_hints(RetryDefaultsKwargs) == {}


def test_logging_kwargs_keys() -> None:
    assert get_type_hints(LoggingDefaultsKwargs) == {}


def test_defaults_kwargs_combines() -> None:
    assert get_type_hints(DefaultsKwargs) == {}
