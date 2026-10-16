"""Logging utilities for retry decorators."""

import dataclasses as dc
import logging
import sys
from collections.abc import (
    Mapping,
)
from enum import (
    IntEnum,
)
from typing import (
    Any,
    Final,
    Literal,
    assert_never,
    overload,
)

type _LogKind = Literal["success", "retry", "failure", "sleep"]


class LogLevel(IntEnum):
    """
    Log level for a retry log kind.

    Extends :mod:`logging` levels with ``OFF`` to disable a kind
    entirely.
    """

    OFF = 0
    """Disable logging for this kind."""
    DEBUG = logging.DEBUG
    """Debug level."""
    INFO = logging.INFO
    """Info level."""
    WARNING = logging.WARNING
    """Warning level."""
    ERROR = logging.ERROR
    """Error level."""
    CRITICAL = logging.CRITICAL
    """Critical level."""


def _make_default_logger() -> logging.Logger:
    """
    Create the default logger writing to stdout or stderr.

    Uses :data:`sys.stdout` when available, otherwise falls back to
    :data:`sys.stderr`. If neither stream is available, no handler is
    attached.

    Returns
    -------
    logging.Logger
        default logger

    """
    logger = logging.getLogger("retry")
    stream = sys.stdout or sys.stderr

    if not logger.handlers and stream is not None:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            logging.Formatter(
                "{asctime} [{levelname:^9}] {fname} "
                "[{retry_index}/{attempts}] "
                "({elapsed:.2f}s) [{exception_type}]: {message}",
                style="{",
                defaults={
                    "fname": "<unknown>",
                    "retry_index": "?",
                    "attempts": "?",
                    "elapsed": 0.0,
                    "exception_type": "-",
                },
            )
        )
        logger.addHandler(handler)

    return logger


_DEFAULT_LOGGER: Final[logging.Logger] = _make_default_logger()


@dc.dataclass(frozen=True, slots=True)
class LoggerConfig:
    """
    Immutable snapshot of logging configuration.

    Attributes
    ----------
    level_success : LogLevel
        Level for success messages, or ``OFF`` to disable.
    level_retry : LogLevel
        Level for retry messages, or ``OFF`` to disable.
    level_failure : LogLevel
        Level for failure messages, or ``OFF`` to disable.
    level_sleep : LogLevel
        Level for sleep messages, or ``OFF`` to disable.
    traceback_min_level : LogLevel
        Minimum level at which a traceback is attached to the log
        record.
    disable_logging : bool
        If ``True``, all logging is skipped.
    disable_warnings : bool
        If ``True``, warnings are suppressed.

    """

    level_success: LogLevel
    level_retry: LogLevel
    level_failure: LogLevel
    level_sleep: LogLevel
    traceback_min_level: LogLevel
    disable_logging: bool
    disable_warnings: bool


class Log:
    """
    Kind-aware logging wrapper around a :class:`~fastretry._utils.logs.LoggerConfig`.

    Use :meth:`use` to select a logger kind
    and then call the result to emit a message::

        log = Log(config)
        log.use("retry")("Error executing '%s'", fname)
        log.use("failure")("Failed: %s", fname, last_exception=exc)

    Parameters
    ----------
    config : LoggerConfig
        Immutable logging configuration.

    """

    __slots__ = ("_bound", "_config")

    def __init__(
        self,
        config: LoggerConfig,
    ) -> None:
        self._config = config
        self._bound: dict[_LogKind, _BoundLog[_LogKind]] = {
            "retry": _BoundLog(self, "retry"),
            "failure": _BoundLog(self, "failure"),
            "sleep": _BoundLog(self, "sleep"),
            "success": _BoundLog(self, "success"),
        }

    @overload
    def use(self, log_kind: Literal["retry"]) -> '_BoundLog[Literal["retry"]]': ...

    @overload
    def use(self, log_kind: Literal["failure"]) -> '_BoundLog[Literal["failure"]]': ...

    @overload
    def use(self, log_kind: Literal["sleep"]) -> '_BoundLog[Literal["sleep"]]': ...

    @overload
    def use(self, log_kind: Literal["success"]) -> '_BoundLog[Literal["success"]]': ...

    def use(self, log_kind: _LogKind) -> "_BoundLog[Any]":
        """
        Select a logger kind.

        Returns a cached callable that emits messages using the chosen
        logger. The returned object can be stored and reused::

            retry_log = log.use("retry")
            retry_log("first message")
            retry_log("second message")

        Parameters
        ----------
        log_kind : _LogKind
            Logger kind: ``"retry"``, ``"failure"``, ``"sleep"``, or
            ``"success"``.

        Returns
        -------
        _BoundLog
            Callable that emits messages using the selected logger.

        """
        return self._bound[log_kind]

    def record(
        self,
        *,
        log_kind: _LogKind,
        message: str,
        args: tuple[Any, ...],
        last_exception: BaseException | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> bool:
        """
        Record a log message for ``log_kind`` and dispatch it.

        Low-level entry point: no overloading, no caching, no per-kind
        argument checks. Prefer :meth:`use` unless you have a specific
        reason to call this directly.

        Parameters
        ----------
        log_kind : _LogKind
            Logger kind.
        message : str
            ``%``-style format string.
        args : tuple[Any, ...]
            Format arguments.
        last_exception : BaseException | None, ``optional``
            Exception to attach as ``exc_info`` when the message's level is
            at or above :attr:`~fastretry._utils.logs.LoggerConfig.traceback_min_level`.
        extra : Mapping[str, object] | None, ``optional``
            Additional fields to attach to the log record via the ``logging``
            ``extra`` argument. Useful for structured logging backends
            (Sentry, Datadog). Ignored by custom loggers that do not accept
            ``extra``.

        Returns
        -------
        bool
            - ``True`` if the message was dispatched,
            - ``False`` if logging is disabled or the level for
            ``log_kind`` is ``OFF``.

        """
        log_level = self._resolve_log_kind(log_kind)

        if self._config.disable_logging or log_level == LogLevel.OFF:
            return False

        kwargs: dict[str, Any] = {}

        if log_level >= self._config.traceback_min_level and last_exception is not None:
            kwargs["exc_info"] = last_exception

        if extra:
            kwargs["extra"] = dict(extra)

        _DEFAULT_LOGGER.log(log_level, message, *args, **kwargs)
        return True

    def _resolve_log_kind(
        self,
        log_kind: _LogKind,
    ) -> LogLevel:
        config = self._config

        match log_kind:
            case "sleep":
                return config.level_sleep
            case "success":
                return config.level_success
            case "retry":
                return config.level_retry
            case "failure":
                return config.level_failure
            case _:
                assert_never(log_kind)


class _BoundLog[LK: _LogKind]:
    """
    Callable bound to a specific logger kind.

    Created by :meth:`~fastretry._utils.logs.Log.use`
    and cached in :class:`~fastretry._utils.logs.Log`.
    Not intended to be instantiated directly.

    Parameters
    ----------
    log : Log
        Parent logger.
    log_kind : _LogKind
        Bound logger kind.

    """

    __slots__ = ("_log", "_log_kind")

    def __init__(
        self,
        log: Log,
        log_kind: LK,
    ) -> None:
        self._log = log
        self._log_kind: LK = log_kind

    @overload
    def __call__(
        self: '_BoundLog[Literal["success", "sleep"]]',
        message: str,
        /,
        *args: object,
        extra: Mapping[str, object] | None = None,
    ) -> bool: ...

    @overload
    def __call__(
        self: '_BoundLog[Literal["retry", "failure"]]',
        message: str,
        /,
        *args: object,
        last_exception: BaseException | None,
        extra: Mapping[str, object] | None = None,
    ) -> bool: ...

    def __call__(
        self,
        message: str,
        /,
        *args: object,
        last_exception: BaseException | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> bool:
        """
        Emit a log message using the bound logger kind.

        Parameters
        ----------
        message : str
            ``%``-style format string.
        *args : object
            Format arguments.
        last_exception : BaseException | None, ``optional``
            Exception to attach as ``exc_info`` when the message's level is
            at or above :attr:`~fastretry._utils.logs.LoggerConfig.traceback_min_level`.
        extra : Mapping[str, object] | None, ``optional``
            Additional fields to attach to the log record via the
            ``logging`` ``extra`` argument.

        Returns
        -------
        bool
            - ``True`` if the message was dispatched,
            - ``False`` if logging is disabled or the level for
            the bound kind is ``OFF``.

        """
        return self._log.record(
            log_kind=self._log_kind,
            message=message,
            args=args,
            last_exception=last_exception,
            extra=extra,
        )
