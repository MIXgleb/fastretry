"""Tests for config namespace."""

import pytest

from retry import (
    config,
)
from retry._defaults import (
    get_defaults,
    global_defaults,
)
from retry._utils.callbacks import (
    default_on_success,
)
from retry._utils.logs import (
    LogLevel,
)


def test_retry_sets_global() -> None:
    config.retry(attempts=7)
    assert global_defaults.attempts == 7


def test_logging_sets_global() -> None:
    config.logging(level_retry=LogLevel.INFO)
    assert global_defaults.level_retry == LogLevel.INFO


def test_reset() -> None:
    config.retry(attempts=7)
    config.reset()
    assert global_defaults.attempts == 1


def test_context_isolated() -> None:
    config.retry(attempts=1)

    with config.context(attempts=5):
        assert get_defaults().attempts == 5
    assert get_defaults().attempts == 1


def test_context_mutation_inside() -> None:
    config.retry(attempts=1)

    with config.context():
        config.retry(attempts=9)
        assert get_defaults().attempts == 9
        assert global_defaults.attempts == 1

    assert get_defaults().attempts == 1


def test_context_nested() -> None:
    with config.context(attempts=2):
        with config.context(attempts=3):
            assert get_defaults().attempts == 3
        assert get_defaults().attempts == 2


def test_retry_unknown_key() -> None:
    with pytest.raises(AttributeError, match="Unknown default"):
        config.retry(unknown=1)


def test_retry_ignores_unset() -> None:
    assert global_defaults.on_success is default_on_success
    config.retry(attempts=7)
    assert global_defaults.attempts == 7
    assert global_defaults.on_success is default_on_success
    config.retry(delay=5)
    assert global_defaults.delay == 5
    assert global_defaults.attempts == 7
    assert global_defaults.on_success is default_on_success


def test_reset_inside_context() -> None:
    config.retry(attempts=5)

    with config.context(attempts=9):
        config.reset()
        assert get_defaults().attempts == 1
        assert global_defaults.attempts == 5

    assert global_defaults.attempts == 5
