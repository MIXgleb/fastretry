"""
The built-in handler must respect the application's logging configuration.

``Log.record`` claims to report whether a message was dispatched. It used to
return ``True`` as soon as ``logger.log`` was called, so a record the logger
filters out was treated as delivered and the swallowed-exception warning was
never emitted. Installing the handler also overwrote an explicit logger level
with ``DEBUG``.
"""

import io
import logging
import warnings
from collections.abc import (
    Generator,
)
from contextlib import (
    redirect_stderr,
)
from typing import (
    Literal,
    NoReturn,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry._utils.logs import (
    FASTRETRY_LOGGER_NAME,
    Log,
    LoggerConfig,
    LogLevel,
)


@pytest.fixture
def retry_logger() -> Generator[logging.Logger]:
    """
    Isolate the shared logger and the lazy handler state.

    Yields
    ------
    logging.Logger
        The ``fastretry`` logger with no handlers and no level.

    """
    logger = logging.getLogger(FASTRETRY_LOGGER_NAME)
    handlers = list(logger.handlers)
    level = logger.level

    logger.handlers = []
    logger.setLevel(logging.NOTSET)
    Log._installed_handler = False

    yield logger

    logger.handlers = handlers
    logger.setLevel(level)
    Log._installed_handler = False


def _config(**overrides: LogLevel) -> LoggerConfig:
    levels: dict[str, LogLevel] = {
        "level_success": LogLevel.OFF,
        "level_retry": LogLevel.WARNING,
        "level_failure": LogLevel.ERROR,
        "level_sleep": LogLevel.OFF,
        "traceback_min_level": LogLevel.ERROR,
    }
    levels.update(overrides)

    return LoggerConfig(disable_logging=False, install_default_handler=True, **levels)


def test_application_logger_level_is_kept(
    retry_logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retry_logger.setLevel(logging.ERROR)

    @retry(attempts=2, delay=0, disable_warnings=True)
    def fn() -> NoReturn:
        msg = "boom"
        raise ValueError(msg)

    with pytest.RaisesGroup(ValueError, ValueError):
        fn()

    messages = [record.getMessage() for record in caplog.records]

    assert retry_logger.level == logging.ERROR
    assert not any("Try 1 of 2" in message for message in messages)
    assert any("Failed the execution of the function" in message for message in messages)


def test_explicit_level_survives_the_built_in_handler(
    retry_logger: logging.Logger,
) -> None:
    """The install path is only taken when nothing in the chain has a handler."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    root.handlers = []

    try:
        retry_logger.setLevel(logging.ERROR)

        @retry(attempts=2, delay=0, disable_warnings=True)
        def fn() -> NoReturn:
            msg = "boom"
            raise ValueError(msg)

        out = io.StringIO()

        with redirect_stderr(out), pytest.RaisesGroup(ValueError, ValueError):
            fn()
    finally:
        root.handlers = saved_handlers

    lines = out.getvalue().strip().splitlines()

    assert retry_logger.level == logging.ERROR
    assert not any("Try 1 of 2" in line for line in lines)
    assert any("Failed the execution of the function" in line for line in lines)


def test_record_reports_a_filtered_message(
    retry_logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retry_logger.setLevel(logging.ERROR)
    log = Log(config=_config())

    dispatched = log.record(log_kind="retry", message="filtered", args=())
    delivered = log.record(log_kind="failure", message="delivered", args=())

    messages = [record.getMessage() for record in caplog.records]

    assert dispatched is False
    assert delivered is True
    assert "filtered" not in messages
    assert "delivered" in messages


def test_globally_disabled_logging_is_reported(retry_logger: logging.Logger) -> None:
    assert retry_logger.name == FASTRETRY_LOGGER_NAME

    log = Log(config=_config())
    logging.disable(logging.CRITICAL)

    try:
        assert log.record(log_kind="failure", message="muted", args=()) is False
    finally:
        logging.disable(logging.NOTSET)


def test_swallowed_callback_error_is_not_lost_when_logging_is_disabled(
    retry_logger: logging.Logger,
) -> None:
    assert retry_logger.name == FASTRETRY_LOGGER_NAME

    def broken(_stats: object) -> None:
        msg = "callback broke"
        raise RuntimeError(msg)

    @retry(attempts=1, callbacks={"on_success": broken})
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1

    logging.disable(logging.CRITICAL)

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert fn() == 1
    finally:
        logging.disable(logging.NOTSET)

    messages = [str(item.message) for item in caught]
    assert any("Swallowed exception" in message for message in messages)
