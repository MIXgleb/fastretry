"""
Logging utilities for retry decorators.

Provides the :class:`Log` helper — a level-aware wrapper around a logging
configuration that centralizes logger selection, traceback handling, and
keyword fallback.
"""

import re
from typing import (
    TYPE_CHECKING,
    Literal,
    Protocol,
    assert_never,
)

from retry._utils._warnings import (
    warning,
)

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
    )
    from typing import (
        Any,
    )

    from retry._types import (
        LoggerType,
    )


type _LogLevel = Literal["info", "warning", "error"]

_UNEXPECTED_KWARG_RE = re.compile(
    r"got an unexpected keyword argument ['\"](?P<name>[^'\"]+)['\"]",
)


class _LogContext(Protocol):
    """
    Interface for objects that expose logging configuration.

    Implemented by ``BaseRetrying``. Any object with these attributes can
    be passed to :class:`Log`.
    """

    logger_info: LoggerType | None
    logger_warning: LoggerType | None
    logger_error: LoggerType | None
    logger_traceback_kwarg: str
    disable_logging: bool
    disable_info_logging: bool
    disable_warning_logging: bool
    disable_error_logging: bool
    include_traceback_in_warning_log: bool
    include_traceback_in_error_log: bool
    disable_warnings: bool


class Log:
    """
    Level-aware logging wrapper around a :class:`_LogContext`.

    Provides ``info``, ``warning``, and ``error`` methods that select the
    appropriate logger and traceback configuration from the context.

    Parameters
    ----------
    ctx : _LogContext
        Logging configuration (usually a ``BaseRetrying`` instance).

    """

    __slots__ = ("_ctx",)

    def __init__(self, ctx: _LogContext) -> None:
        self._ctx = ctx

    def info(
        self,
        message: str,
        *args: object,
    ) -> None:
        """
        Emit an info-level log message.

        Parameters
        ----------
        message : str
            ``%``-style format string.
        *args : object
            Format arguments.

        """
        self._emit(
            level="info",
            message=message,
            args=args,
            intercepted_exception=None,
        )

    def warning(
        self,
        message: str,
        *args: object,
        intercepted_exception: BaseException | None = None,
    ) -> None:
        """
        Emit a warning-level log message.

        Parameters
        ----------
        message : str
            ``%``-style format string.
        *args : object
            Format arguments.
        intercepted_exception : BaseException | None, optional
            Exception to pass via ``logger_traceback_kwarg`` if traceback
            logging is enabled.

        """
        self._emit(
            level="warning",
            message=message,
            args=args,
            intercepted_exception=intercepted_exception,
        )

    def error(
        self,
        message: str,
        *args: object,
        intercepted_exception: BaseException | None = None,
    ) -> None:
        """
        Emit an error-level log message.

        Parameters
        ----------
        message : str
            ``%``-style format string.
        *args : object
            Format arguments.
        intercepted_exception : BaseException | None, optional
            Exception to pass via ``logger_traceback_kwarg`` if traceback
            logging is enabled.

        """
        self._emit(
            level="error",
            message=message,
            args=args,
            intercepted_exception=intercepted_exception,
        )

    def _emit(
        self,
        *,
        level: _LogLevel,
        message: str,
        args: tuple[Any, ...],
        intercepted_exception: BaseException | None,
    ) -> None:
        """Resolve logger and dispatch the message."""
        logger, disable_level, include_traceback = self._resolve(level)

        if self._ctx.disable_logging or disable_level or logger is None:
            return

        kwargs: dict[str, Any] = {}

        if include_traceback and intercepted_exception is not None:
            kwargs[self._ctx.logger_traceback_kwarg] = intercepted_exception

        self._safe_log_with_fallback(
            logger=logger,
            message=message,
            args=args,
            kwargs=kwargs,
            level=level,
        )

    def _resolve(
        self,
        level: _LogLevel,
    ) -> tuple[LoggerType | None, bool, bool]:
        """
        Return the logger, disable flag, and traceback flag for a level.

        Parameters
        ----------
        level : {"info", "warning", "error"}
            Log level.

        Returns
        -------
        tuple[LoggerType | None, bool, bool]
            Logger, per-level disable flag, and traceback flag.

        """
        ctx = self._ctx

        match level:
            case "info":
                return ctx.logger_info, ctx.disable_info_logging, False
            case "warning":
                return (
                    ctx.logger_warning,
                    ctx.disable_warning_logging,
                    ctx.include_traceback_in_warning_log,
                )
            case "error":
                return (
                    ctx.logger_error,
                    ctx.disable_error_logging,
                    ctx.include_traceback_in_error_log,
                )
            case _:
                assert_never(level)

    def _safe_log_with_fallback(
        self,
        *,
        logger: Callable[..., Any],
        message: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        level: _LogLevel,
    ) -> None:
        """
        Call ``logger``, dropping keyword arguments it does not accept.

        If the logger raises ``TypeError`` because a keyword argument is
        not accepted, that keyword is removed from ``kwargs``, a warning
        is emitted, and the call is retried. Any other ``TypeError`` is
        re-raised.

        Parameters
        ----------
        logger : Callable
            Logger callable to invoke.
        message : str
            ``%``-style format string.
        args : tuple[Any, ...]
            Format arguments.
        kwargs : dict[str, Any]
            Keyword arguments to pass. Modified in place as unsupported
            keys are dropped.
        level : _LogLevel
            Log level, used in warning messages.

        Raises
        ------
        TypeError
            Logger raised ``TypeError`` unrelated to keyword arguments.

        """
        while kwargs:
            try:
                logger(message, *args, **kwargs)
            except TypeError as exc:
                if "got an unexpected keyword argument" not in str(exc):
                    raise

                key = self._extract_unexpected_kwarg(exc)

                if key is None or key not in kwargs:
                    raise

                warning(
                    f"\n\tLogger for level {level!r} does not accept "
                    f"{key!r} kwarg; logging without it.",
                    disable_warnings=self._ctx.disable_warnings,
                    stacklevel=4,
                )
                kwargs.pop(key)
            else:
                return

        logger(message, *args)

    @staticmethod
    def _extract_unexpected_kwarg(exc: TypeError) -> str | None:
        """
        Extract the offending keyword name from a ``TypeError`` message.

        Expected format::

            <callable>() got an unexpected keyword argument '<name>'

        Parameters
        ----------
        exc : TypeError
            Exception to parse.

        Returns
        -------
        str | None
            The keyword name, or ``None`` if the message doesn't match.

        """
        match = _UNEXPECTED_KWARG_RE.search(str(exc))
        return match.group("name") if match else None
