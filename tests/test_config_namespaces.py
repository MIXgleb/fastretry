"""``config.retry`` and ``config.logging`` must not configure each other.

Both write into one ``Defaults`` instance, so ``config.logging(attempts=5)``
used to reconfigure retrying for the whole process without a word, and a
rejected batch used to leave the values before the bad key applied.
"""

import pytest

from fastretry._configs.config import (
    config,
)
from fastretry._configs.defaults import (
    get_defaults,
    global_defaults,
)
from fastretry.logging import (
    LogLevel,
)


def test_logging_namespace_rejects_retry_options() -> None:
    with pytest.raises(TypeError, match=r"`attempts` is configured via `config\.retry"):
        config.logging(attempts=5)  # type: ignore[call-arg]


def test_retry_namespace_rejects_logging_options() -> None:
    with pytest.raises(TypeError, match=r"`level_retry` is configured via `config\.logging"):
        config.retry(level_retry=LogLevel.DEBUG)  # type: ignore[call-arg]


def test_rejected_logging_call_does_not_change_retry_defaults() -> None:
    with pytest.raises(TypeError):
        config.logging(attempts=5)  # type: ignore[call-arg]

    assert global_defaults.attempts == 1


def test_rejected_retry_call_does_not_change_logging_defaults() -> None:
    with pytest.raises(TypeError):
        config.retry(level_retry=LogLevel.DEBUG)  # type: ignore[call-arg]

    assert global_defaults.level_retry is LogLevel.WARNING


def test_each_namespace_still_accepts_its_own_options() -> None:
    config.retry(attempts=4, on_retry=None)
    config.logging(level_failure=LogLevel.CRITICAL, install_default_handler=False)

    assert global_defaults.attempts == 4
    assert global_defaults.on_retry is None
    assert global_defaults.level_failure is LogLevel.CRITICAL
    assert global_defaults.install_default_handler is False


def test_unknown_option_changes_nothing() -> None:
    with pytest.raises(AttributeError, match="Unknown default: 'bogus'"):
        config.retry(attempts=5, bogus=1)  # type: ignore[call-arg]

    assert global_defaults.attempts == 1


def test_context_accepts_both_groups() -> None:
    with config.context(attempts=3, level_retry=LogLevel.DEBUG):
        assert get_defaults().attempts == 3
        assert get_defaults().level_retry is LogLevel.DEBUG
        assert global_defaults.attempts == 1

    assert get_defaults().attempts == 1
