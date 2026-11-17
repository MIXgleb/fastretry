"""Tests for Log and LoggerConfig."""

import dataclasses as dc
import io
import logging
import sys
from collections.abc import (
    Generator,
)

import pytest
from pytest_mock import (
    MockerFixture,
)

from fastretry._utils.logs import (
    _DEFAULT_LOGGER,
    _LOGGER_NAME,
    Log,
    LoggerConfig,
    LogLevel,
    _StderrHandler,
)


@pytest.fixture
def _isolate_retry_logger() -> Generator[None]:
    """Isolate the shared logger and the lazy default handler state."""
    logger = logging.getLogger(_LOGGER_NAME)
    handlers = list(logger.handlers)
    level = logger.level

    logger.handlers = []
    logger.setLevel(logging.NOTSET)
    Log._installed_handler = False

    yield

    logger.handlers = handlers
    logger.setLevel(level)
    Log._installed_handler = False


def _make_record(message: str = "hello") -> logging.LogRecord:
    """
    Build a log record belonging to the package logger.

    Parameters
    ----------
    message : str, ``optional``
        Message of the record, by default ``"hello"``.

    Returns
    -------
    logging.LogRecord
        Record belonging to the ``"retry"`` logger.

    """
    return logging.LogRecord(
        _LOGGER_NAME,
        logging.WARNING,
        __file__,
        1,
        message,
        (),
        None,
    )


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
        install_default_handler=True,
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
            install_default_handler=True,
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
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    result = log.record(log_kind=log_kind, message="m", args=())
    assert result is True
    mock_log.assert_called_once()
    assert mock_log.call_args.args[0] == expected_level


def test_record_passes_args(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    _ = log.record(log_kind="retry", message="m %s", args=("a",))
    args, _ = mock_log.call_args
    assert args[1] == "m %s"
    assert args[2] == "a"


def test_record_failure_with_exc(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
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
        install_default_handler=True,
    )
    log = Log(cfg)
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    _ = log.record(log_kind="failure", message="m", args=(), last_exception=ValueError())
    _, kwargs = mock_log.call_args
    assert "exc_info" not in kwargs


def test_record_with_extra(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    _ = log.record(log_kind="retry", message="m", args=(), extra={"key": "val"})
    _, kwargs = mock_log.call_args
    assert kwargs["extra"] == {"key": "val"}


def test_record_without_extra(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
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
        install_default_handler=True,
    )
    log = Log(cfg)
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    assert log.record(log_kind="retry", message="m", args=()) is False
    mock_log.assert_not_called()


def test_use_returns_bound(log: Log) -> None:
    bound = log.use("retry")
    assert bound is log.use("retry")


def test_bound_call(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    bound = log.use("retry")
    result = bound("m %s", "a")
    assert result is True
    mock_log.assert_called_once()


def test_bound_failure_with_exc(log: Log, mocker: MockerFixture) -> None:
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")
    exc = ValueError()
    _ = log.use("failure")("m", last_exception=exc)
    _, kwargs = mock_log.call_args
    assert kwargs["exc_info"] is exc


@pytest.mark.usefixtures("_isolate_retry_logger")
def test_default_handler_installed_on_first_record(
    log: Log,
    mocker: MockerFixture,
) -> None:
    _ = mocker.patch.object(_DEFAULT_LOGGER, "hasHandlers", return_value=False)
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")

    result = log.record(log_kind="retry", message="m", args=())

    assert result is True
    mock_log.assert_called_once()
    handlers = _DEFAULT_LOGGER.handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], _StderrHandler)
    assert _DEFAULT_LOGGER.level == logging.DEBUG
    assert log._installed_handler is True


@pytest.mark.usefixtures("_isolate_retry_logger")
def test_default_handler_installed_once(
    log: Log,
    mocker: MockerFixture,
) -> None:
    _ = mocker.patch.object(_DEFAULT_LOGGER, "hasHandlers", return_value=False)
    _ = mocker.patch.object(_DEFAULT_LOGGER, "log")

    _ = log.record(log_kind="retry", message="m", args=())
    _ = log.record(log_kind="retry", message="m", args=())

    assert len(_DEFAULT_LOGGER.handlers) == 1


@pytest.mark.usefixtures("_isolate_retry_logger")
def test_default_handler_not_installed_when_logger_configured(
    log: Log,
    mocker: MockerFixture,
) -> None:
    _ = mocker.patch.object(_DEFAULT_LOGGER, "log")
    user_handler = logging.NullHandler()
    _DEFAULT_LOGGER.addHandler(user_handler)

    _ = log.record(log_kind="retry", message="m", args=())

    assert _DEFAULT_LOGGER.handlers == [user_handler]
    assert log._installed_handler is True


@pytest.mark.usefixtures("_isolate_retry_logger")
def test_default_handler_not_installed_when_ancestor_configured(
    log: Log,
    mocker: MockerFixture,
) -> None:
    _ = mocker.patch.object(_DEFAULT_LOGGER, "log")
    _ = mocker.patch.object(_DEFAULT_LOGGER, "hasHandlers", return_value=True)

    _ = log.record(log_kind="retry", message="m", args=())

    assert _DEFAULT_LOGGER.handlers == []
    assert log._installed_handler is True


@pytest.mark.usefixtures("_isolate_retry_logger")
def test_default_handler_disabled(mocker: MockerFixture) -> None:
    log = Log(
        LoggerConfig(
            level_success=LogLevel.OFF,
            level_retry=LogLevel.WARNING,
            level_failure=LogLevel.ERROR,
            level_sleep=LogLevel.OFF,
            traceback_min_level=LogLevel.ERROR,
            disable_logging=False,
            install_default_handler=False,
        )
    )
    mock_log = mocker.patch.object(_DEFAULT_LOGGER, "log")

    result = log.record(log_kind="retry", message="m", args=())

    assert result is True
    mock_log.assert_called_once()
    handlers = _DEFAULT_LOGGER.handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.NullHandler)
    assert log._installed_handler is True


def test_stderr_handler_follows_current_stream(mocker: MockerFixture) -> None:
    handler = _StderrHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    stream = io.StringIO()
    _ = mocker.patch.object(sys, "stderr", stream)

    handler.emit(_make_record("hello"))

    assert stream.getvalue() == "hello\n"


def test_stderr_handler_without_any_stream(mocker: MockerFixture) -> None:
    handler = _StderrHandler()
    handler.stream = None
    _ = mocker.patch.object(sys, "stderr", None)
    _ = mocker.patch.object(sys, "__stderr__", None)

    handler.emit(_make_record())

    assert handler.stream is None


def test_build_default_handler_formats_record() -> None:
    handler = Log._build_default_handler()
    formatter = handler.formatter
    assert formatter is not None

    record = _make_record("boom")
    record.__dict__.update({
        "fname": "fn",
        "retry_index": 1,
        "attempts": 3,
        "attempt_duration": 0.054321,
        "total_elapsed": 0.5,
        "exception_type": "ValueError",
    })

    formatted = formatter.format(record)

    assert "fn [1/3 in 0.05s] (0.50s) [ValueError]: boom" in formatted


def test_build_default_handler_uses_defaults() -> None:
    handler = Log._build_default_handler()
    formatter = handler.formatter
    assert formatter is not None

    formatted = formatter.format(_make_record("boom"))

    assert "<unknown> [?/? in 0.00s] (0.00s) [-]: boom" in formatted


def test_incorrect_log_kind() -> None:
    cfg = LoggerConfig(
        level_success=LogLevel.OFF,
        level_retry=LogLevel.OFF,
        level_failure=LogLevel.OFF,
        level_sleep=LogLevel.OFF,
        traceback_min_level=LogLevel.OFF,
        disable_logging=True,
        install_default_handler=True,
    )
    log = Log(cfg)

    with pytest.raises(AssertionError):
        log.record(log_kind="incorrect_log_kind", message="test", args=())
