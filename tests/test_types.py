"""Tests for TypedDict definitions."""

import sys
from typing import (
    get_type_hints,
)

if sys.version_info >= (3, 15):
    from typing import (
        is_typeddict,
    )
else:
    from typing_extensions import (
        is_typeddict,
    )

from retry._types import (
    DefaultsKwargs,
    LoggingDefaultsKwargs,
    RetryDefaultsKwargs,
    RetryKwargs,
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


def test_retry_options_all_optional() -> None:
    """All keys in RetryOptions are optional (total=False)."""
    assert _RetryOptions.__required_keys__ == frozenset()
    assert _RetryOptions.__optional_keys__ == frozenset({
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


def test_retry_kwargs_inherits_options() -> None:
    """RetryKwargs extends RetryOptions."""
    hints = get_type_hints(RetryKwargs)
    assert "attempts" in hints
    assert "return_default_value" in hints
    assert "jitter" in hints
    assert "callbacks" in hints


def test_logging_kwargs_keys() -> None:
    hints = get_type_hints(LoggingDefaultsKwargs)
    assert "level_retry" in hints
    assert "level_failure" in hints
    assert "traceback_min_level" in hints


def test_defaults_kwargs_combines() -> None:
    """DefaultsKwargs combines retry and logging options."""
    hints = get_type_hints(DefaultsKwargs)
    assert "attempts" in hints
    assert "level_retry" in hints
    assert "jitter_for_fixed" in hints
