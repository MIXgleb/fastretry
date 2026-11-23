"""Tests for option validation."""

import dataclasses as dc
from concurrent.futures import (
    ThreadPoolExecutor,
)
from typing import (
    get_args,
)

import pytest

from fastretry._compat.sentinels import (
    UNSET,
)
from fastretry._compat.types import (
    LoggingDefaultsKwargs,
    RetryDefaultsKwargs,
    RetryKwargs,
    RetryWithExecutorKwargs,
)
from fastretry._configs.config import (
    config,
)
from fastretry._configs.defaults import (
    Defaults,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry._utils.callbacks import (
    CALLBACK_NAMES,
    RetryCallbacks,
)
from fastretry._utils.delays import (
    JITTER_STRATEGIES,
    JitterStrategy,
)
from fastretry._utils.logs import (
    LogLevel,
)
from fastretry._utils.shared_loop import (
    ASYNC_CALLBACK_MODES,
    AsyncCallbackMode,
)
from fastretry._utils.stats import (
    DecoratorOptions,
)
from fastretry._utils.validations import (
    GLOBAL_LOGGING_OPTIONS,
    GLOBAL_RETRY_OPTIONS,
    RETRY_OPTIONS,
    OptionsValidator,
)
from fastretry._utils.warnings import (
    Warnings,
)


def test_option_sets_match_typed_dicts() -> None:
    assert frozenset(RetryKwargs.__optional_keys__) == RETRY_OPTIONS
    assert RETRY_OPTIONS | {"executor"} == frozenset(RetryWithExecutorKwargs.__optional_keys__)
    assert frozenset(RetryDefaultsKwargs.__optional_keys__) - RETRY_OPTIONS == GLOBAL_RETRY_OPTIONS
    assert frozenset(LoggingDefaultsKwargs.__optional_keys__) == GLOBAL_LOGGING_OPTIONS


def test_callback_names_match_typed_dict() -> None:
    assert frozenset(RetryCallbacks.__optional_keys__) == CALLBACK_NAMES


def test_retry_accepts_valid_options() -> None:
    @retry(attempts=2, delay=0, jitter="none", callbacks={"on_retry": None})
    def fn() -> int:
        return 1

    assert fn() == 1


def test_retry_rejects_unknown_option() -> None:
    with pytest.raises(
        TypeError,
        match=r"^retry\(\) got an unexpected keyword argument 'foo'$",
    ):
        retry(foo=1)


def test_retry_suggests_close_option() -> None:
    with pytest.raises(
        TypeError,
        match=r"unexpected keyword argument 'attempt'; did you mean `attempts`\?$",
    ):
        retry(attempt=3)


def test_retry_suggests_global_option() -> None:
    with pytest.raises(
        TypeError,
        match=r"did you mean the global option `unwrap_single_exception`",
    ):
        retry(unwrap_single_exceptions=True)


@pytest.mark.parametrize(
    ("option", "value", "match"),
    [
        (
            "unwrap_single_exception",
            True,
            (
                r"^`unwrap_single_exception` is a global option, "
                r"configure it via `config\.retry\(\.\.\.\)`$"
            ),
        ),
        (
            "jitter_for_fixed",
            "equal",
            r"^`jitter_for_fixed` is a global option, configure it via `config\.retry\(\.\.\.\)`$",
        ),
        (
            "level_retry",
            LogLevel.WARNING,
            r"^`level_retry` is a global option, configure it via `config\.logging\(\.\.\.\)`$",
        ),
        (
            "install_default_handler",
            False,
            (
                r"^`install_default_handler` is a global option, "
                r"configure it via `config\.logging\(\.\.\.\)`$"
            ),
        ),
    ],
)
def test_retry_rejects_global_option(
    option: str,
    value: object,
    match: str,
) -> None:
    with pytest.raises(TypeError, match=match):
        retry(**{option: value})


def test_retry_rejects_executor() -> None:
    with (
        ThreadPoolExecutor(max_workers=1) as pool,
        pytest.raises(
            TypeError,
            match=r"^`executor` is only supported by `retry_async\(\.\.\.\)`$",
        ),
    ):
        retry(executor=pool)


async def test_retry_async_accepts_executor() -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        wrapped = retry_async(attempts=1, executor=pool)(lambda: 1)

        assert await wrapped() == 1


@pytest.mark.parametrize(
    ("option", "match"),
    [
        ("attempt", r"unexpected keyword argument 'attempt'; did you mean `attempts`\?$"),
        ("foo", r"^retry_async\(\) got an unexpected keyword argument 'foo'$"),
    ],
)
def test_retry_async_rejects_unknown_option(option: str, match: str) -> None:
    with pytest.raises(TypeError, match=match):
        retry_async(**{option: 1})


def test_retry_async_rejects_global_option() -> None:
    with pytest.raises(
        TypeError,
        match=r"^`async_callback_mode` is a global option, configure it via",
    ):
        retry_async(async_callback_mode="shared_loop_always")


def test_invalid_value_fails_when_decorator_is_applied() -> None:
    with pytest.raises(ValueError, match="jitter must be one of"):
        _ = retry(jitter="sometimes")(lambda: None)


def test_validator_replaces_recoverable_mistakes() -> None:
    validator = OptionsValidator(warnings=Warnings(disable_warnings=True))
    validated = validator.validate_decorator_options(
        options=DecoratorOptions(
            attempts=0,
            return_default_value=UNSET,
            delay=-1.0,
            jitter="none",
            disable_logging=False,
            disable_warnings=True,
            re_raise_exception=True,
            retry_on=ValueError,
            no_retry_on=(),
            executor=None,
        ),
        callbacks=None,
    )

    assert validated.attempts == 1
    assert validated.delay == 0


def test_jitter_strategies_match_literal() -> None:
    assert frozenset(get_args(JitterStrategy.__value__)) == JITTER_STRATEGIES


def test_async_callback_modes_match_literal() -> None:
    assert frozenset(get_args(AsyncCallbackMode.__value__)) == ASYNC_CALLBACK_MODES


#: Invalid value for every field of
#: :class:`~fastretry._configs.defaults.Defaults`, with the error it must
#: produce when a decorator is created.
INVALID_DEFAULTS = (
    ("retry", "attempts", "3", TypeError, "attempts must be an int, got str"),
    ("retry", "delay", "1", TypeError, "delay must be a number of seconds"),
    ("retry", "disable_logging", 1, TypeError, "disable_logging must be a bool"),
    ("retry", "disable_warnings", "no", TypeError, "disable_warnings must be a bool"),
    ("retry", "on_success", "cb", TypeError, "on_success must be callable or None"),
    ("retry", "on_retry", "cb", TypeError, "on_retry must be callable or None"),
    ("retry", "on_failure", "cb", TypeError, "on_failure must be callable or None"),
    ("retry", "retry_on", "ValueError", TypeError, "retry_on must be an exception class"),
    ("retry", "no_retry_on", 42, TypeError, "no_retry_on must be an exception class"),
    ("retry", "jitter_for_exponential", "sometimes", ValueError, "jitter_for_exponential must"),
    ("retry", "jitter_for_fixed", "sometimes", ValueError, "jitter_for_fixed must be"),
    ("retry", "async_callback_mode", "always", ValueError, "async_callback_mode must be"),
    ("retry", "unwrap_single_exception", 1, TypeError, "unwrap_single_exception must be"),
    ("logging", "level_success", 10, TypeError, "level_success must be a LogLevel"),
    ("logging", "level_retry", 20, TypeError, "level_retry must be a LogLevel"),
    ("logging", "level_failure", 40, TypeError, "level_failure must be a LogLevel"),
    ("logging", "level_sleep", 30, TypeError, "level_sleep must be a LogLevel"),
    ("logging", "traceback_min_level", None, TypeError, "traceback_min_level must be a"),
    ("logging", "install_default_handler", "yes", TypeError, "must be a bool, got str"),
)


def test_every_default_is_validated() -> None:
    assert {case[1] for case in INVALID_DEFAULTS} == {field.name for field in dc.fields(Defaults)}


@pytest.mark.parametrize(
    ("namespace", "option", "value", "exception", "match"),
    INVALID_DEFAULTS,
)
def test_invalid_global_default(
    namespace: str,
    option: str,
    value: object,
    exception: type[Exception],
    match: str,
) -> None:
    getattr(config, namespace)(**{option: value})

    with pytest.raises(exception, match=match):
        retry()(lambda: None)
