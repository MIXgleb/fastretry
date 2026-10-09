"""Tests for Log and LoggerConfig."""

import dataclasses as dc
import logging
import sys
from collections.abc import (
    Generator,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

from retry._utils._logs import (
    _RETRY_LOGGER,
    Log,
    LoggerConfig,
    LogLevel,
    _make_retry_logger,
)


@pytest.fixture
def _restore_retry_logger() -> Generator[None]:
    """Save and restore the shared retry logger's handlers and level."""
    logger = logging.getLogger("retry")
    handlers = list(logger.handlers)
    level = logger.level
    propagate = logger.propagate

    yield

    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate


def test_values() -> None:
    assert LogLevel.OFF == 0
    assert LogLevel.DEBUG == logging.DEBUG
    assert LogLevel.INFO == logging.INFO
    assert LogLevel.WARNING == logging.WARNING
    assert LogLevel.ERROR == logging.ERROR
    assert LogLevel.CRITICAL == logging.CRITICAL


def test_frozen() -> None:
    cfg = LoggerConfig(
        level_success=LogLevel.OFF,
        level_retry=LogLevel.WARNING,
        level_failure=LogLevel.ERROR,
        level_sleep=LogLevel.OFF,
        traceback_min_level=LogLevel.ERROR,
        disable_logging=False,
        disable_warnings=False,
    )

    with pytest.raises(dc.FrozenInstanceError):
        cfg.level_success = LogLevel.INFO


@pytest.fixture
def log() -> Log:
    return Log(
        LoggerConfig(
            level_success=LogLevel.OFF,
            level_retry=LogLevel.WARNING,
            level_failure=LogLevel.ERROR,
            level_sleep=LogLevel.OFF,
            traceback_min_level=LogLevel.ERROR,
            disable_logging=False,
            disable_warnings=False,
        )
    )


def test_record_off_level(log: Log) -> None:
    assert log.record(log_kind="success", message="m", args=()) is False


@pytest.mark.parametrize(
    ("log_kind", "expected_level"),
    [
        ("retry", LogLevel.WARNING),
        ("failure", LogLevel.ERROR),
    ],
)
def test_record_levels(
    log: Log,
    mocker: MockerFixture,
    log_kind: str,
    expected_level: LogLevel,
) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    result = log.record(log_kind=log_kind, message="m", args=())
    assert result is True
    mock_log.assert_called_once()
    assert mock_log.call_args.args[0] == expected_level


def test_record_passes_args(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    _ = log.record(log_kind="retry", message="m %s", args=("a",))
    args, _ = mock_log.call_args
    assert args[1] == "m %s"
    assert args[2] == "a"


def test_record_failure_with_exc(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    exc = ValueError("test")
    result = log.record(
        log_kind="failure",
        message="m",
        args=(),
        last_exception=exc,
    )
    assert result is True
    _, kwargs = mock_log.call_args
    assert kwargs["exc_info"] is exc


def test_record_below_traceback_level(mocker: MockerFixture) -> None:
    cfg = LoggerConfig(
        level_success=LogLevel.OFF,
        level_retry=LogLevel.WARNING,
        level_failure=LogLevel.ERROR,
        level_sleep=LogLevel.OFF,
        traceback_min_level=LogLevel.CRITICAL,
        disable_logging=False,
        disable_warnings=False,
    )
    log = Log(cfg)
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    _ = log.record(log_kind="failure", message="m", args=(), last_exception=ValueError())
    _, kwargs = mock_log.call_args
    assert "exc_info" not in kwargs


def test_record_with_extra(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    _ = log.record(log_kind="retry", message="m", args=(), extra={"key": "val"})
    _, kwargs = mock_log.call_args
    assert kwargs["extra"] == {"key": "val"}


def test_record_without_extra(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    _ = log.record(log_kind="retry", message="m", args=())
    _, kwargs = mock_log.call_args
    assert "extra" not in kwargs


def test_disable_logging(mocker: MockerFixture) -> None:
    cfg = LoggerConfig(
        level_success=LogLevel.OFF,
        level_retry=LogLevel.WARNING,
        level_failure=LogLevel.ERROR,
        level_sleep=LogLevel.OFF,
        traceback_min_level=LogLevel.ERROR,
        disable_logging=True,
        disable_warnings=False,
    )
    log = Log(cfg)
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    assert log.record(log_kind="retry", message="m", args=()) is False
    mock_log.assert_not_called()


def test_use_returns_bound(log: Log) -> None:
    bound = log.use("retry")
    assert bound is log.use("retry")


def test_bound_call(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    bound = log.use("retry")
    result = bound("m %s", "a")
    assert result is True
    mock_log.assert_called_once()


def test_bound_failure_with_exc(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_RETRY_LOGGER, "log")
    exc = ValueError()
    _ = log.use("failure")("m", last_exception=exc)
    _, kwargs = mock_log.call_args
    assert kwargs["exc_info"] is exc


@pytest.mark.usefixtures("_restore_retry_logger")
def test_make_retry_logger_falls_back_to_stderr(mocker: MockerFixture) -> None:
    _ = mocker.patch.object(sys, "stdout", None)
    logger = logging.getLogger("retry")
    logger.handlers.clear()

    result = _make_retry_logger()

    assert result.handlers
    assert isinstance(result.handlers[0], logging.StreamHandler)


@pytest.mark.usefixtures("_restore_retry_logger")
def test_make_retry_logger_no_stream(mocker: MockerFixture) -> None:
    _ = mocker.patch.object(sys, "stdout", None)
    _ = mocker.patch.object(sys, "stderr", None)
    logger = logging.getLogger("retry")
    logger.handlers.clear()
    _ = mocker.patch.object(logger, "addHandler")

    _ = _make_retry_logger()

    logger.addHandler.assert_not_called()


@pytest.mark.usefixtures("_restore_retry_logger")
def test_make_retry_logger_existing_handlers(mocker: MockerFixture) -> None:
    logger = logging.getLogger("retry")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    _ = mocker.patch.object(logger, "addHandler")

    _ = _make_retry_logger()

    logger.addHandler.assert_not_called()


@pytest.mark.usefixtures("_restore_retry_logger")
def test_make_retry_logger_creates_handler(mocker: MockerFixture) -> None:
    fake_logger = mocker.MagicMock(spec=logging.Logger)
    fake_logger.handlers = []
    _ = mocker.patch.object(logging, "getLogger", return_value=fake_logger)

    _ = _make_retry_logger()

    fake_logger.addHandler.assert_called_once()


def test_incorrect_log_kind() -> None:
    cfg = LoggerConfig(
        level_success=LogLevel.OFF,
        level_retry=LogLevel.OFF,
        level_failure=LogLevel.OFF,
        level_sleep=LogLevel.OFF,
        traceback_min_level=LogLevel.OFF,
        disable_logging=True,
        disable_warnings=True,
    )
    log = Log(cfg)

    with pytest.raises(AssertionError):
        log.record(log_kind="incorrect_log_kind", message="test", args=())
