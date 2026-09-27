"""
Logging utilities for retry decorators.

Provides the :class:`Log` helper — a kind-aware wrapper around a logging
configuration that centralizes logger selection, traceback handling, and
keyword fallback.
"""

import re
from typing import (
    TYPE_CHECKING,
    Literal,
    assert_never,
    overload,
)

from retry._utils._warnings import (
    Warnings,
)

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
    )
    from typing import (
        Any,
    )

    from retry._types import (
        LogContext,
        LoggerType,
        LogKind,
    )


_UNEXPECTED_KWARG_RE = re.compile(
    r"got an unexpected keyword argument ['\"](?P<name>[^'\"]+)['\"]",
)


class Log:
    """
    Kind-aware logging wrapper around a :class:`LogContext`.

    Use :meth:`use` to select a logger kind and then call the result to
    emit a message::

        log = Log(ctx)
        log.use("retry")("Error executing '%s'", fname)
        log.use("failure")("Failed: %s", fname, intercepted_exception=exc)

    Parameters
    ----------
    ctx : LogContext
        Logging configuration (usually a ``BaseRetrying`` instance).

    """

    __slots__ = ("_bound", "_ctx")

    def __init__(
        self,
        ctx: LogContext,
    ) -> None:
        self._ctx = ctx
        self._bound: dict[LogKind, _BoundLog[LogKind]] = {
            "retry": _BoundLog(self, "retry"),
            "failure": _BoundLog(self, "failure"),
            "sleep": _BoundLog(self, "sleep"),
            "success": _BoundLog(self, "success"),
        }

    @overload
    def use(self, log_kind: Literal["retry"]) -> _BoundLog[Literal["retry"]]: ...

    @overload
    def use(self, log_kind: Literal["failure"]) -> _BoundLog[Literal["failure"]]: ...

    @overload
    def use(self, log_kind: Literal["sleep"]) -> _BoundLog[Literal["sleep"]]: ...

    @overload
    def use(self, log_kind: Literal["success"]) -> _BoundLog[Literal["success"]]: ...

    def use(self, log_kind: LogKind) -> _BoundLog[Any]:
        """
        Select a logger kind.

        Returns a cached callable that emits messages using the chosen
        logger. The returned object can be stored and reused::

            retry_log = log.use("retry")
            retry_log("first message")
            retry_log("second message")

        Parameters
        ----------
        log_kind : LogKind
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
        log_kind: LogKind,
        message: str,
        args: tuple[Any, ...],
        intercepted_exception: Exception | None = None,
    ) -> None:
        """
        Record a log message for ``log_kind`` and dispatch it.

        Low-level entry point: no overloading, no caching, no per-kind
        argument checks. Prefer :meth:`use` unless you have a specific
        reason to call this directly.

        Skips emission when logging is disabled or the logger is ``None``.
        When traceback logging is enabled for the kind and an exception is
        provided, the exception is passed via ``logger_traceback_kwarg``.

        ``intercepted_exception`` is meaningful only for the ``"retry"`` and
        ``"failure"`` kinds, where the logger may accept a traceback keyword
        argument. Passing it for ``"sleep"`` or ``"success"`` is silently
        ignored. Omitting it for ``"retry"`` or ``"failure"`` is allowed —
        the log will be emitted without a traceback.

        Parameters
        ----------
        log_kind : LogKind
            Logger kind.
        message : str
            ``%``-style format string.
        args : tuple[Any, ...]
            Format arguments.
        intercepted_exception : Exception | None, optional
            Exception to pass via ``logger_traceback_kwarg`` if traceback
            logging is enabled for the kind. Ignored for ``"sleep"`` and
            ``"success"``. For ``"retry"`` and ``"failure"`` it is optional;
            when omitted, no traceback is attached.

        """
        logger, include_traceback = self._resolve(log_kind)

        if self._ctx.disable_logging or logger is None:
            return

        kwargs: dict[str, Any] = {}

        if include_traceback and intercepted_exception is not None:
            kwargs[self._ctx.logger_traceback_kwarg] = intercepted_exception

        self._safe_log_with_fallback(
            logger=logger,
            message=message,
            args=args,
            kwargs=kwargs,
            log_kind=log_kind,
        )

    def _resolve(
        self,
        log_kind: LogKind,
    ) -> tuple[LoggerType | None, bool]:
        """
        Return the logger and traceback flag for a log kind.

        Parameters
        ----------
        log_kind : LogKind
            Logger kind.

        Returns
        -------
        tuple[LoggerType | None, bool]
            Logger and traceback flag.

        """
        ctx = self._ctx

        match log_kind:
            case "sleep":
                return ctx.logger_sleep, False
            case "success":
                return ctx.logger_success, False
            case "retry":
                return ctx.logger_retry, ctx.include_traceback_in_retry_log
            case "failure":
                return ctx.logger_failure, ctx.include_traceback_in_failure_log
            case _:
                assert_never(log_kind)

    def _safe_log_with_fallback(
        self,
        *,
        logger: Callable[..., Any],
        message: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        log_kind: LogKind,
    ) -> None:
        """
        Call ``logger``, dropping keyword arguments it does not accept.

        If the logger raises ``TypeError`` because a keyword argument is not
        accepted, that keyword is removed from ``kwargs``, a warning is
        emitted, and the call is retried. Any other ``TypeError`` is
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
            Keyword arguments to pass. Modified in place as unsupported keys
            are dropped.
        log_kind : LogKind
            Logger kind, used in warning messages.

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

                Warnings(disable_warnings=self._ctx.disable_warnings).warn(
                    f"\n\tLogger of kind {log_kind!r} does not accept "
                    f"{key!r} kwarg; logging without it.\n\t"
                    f"Set the correct keyword argument name via "
                    f"configure_logging(logger_traceback_kwarg=...).",
                    stacklevel=6,
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


class _BoundLog[LK: LogKind]:
    """
    Callable bound to a specific logger kind.

    Created by :meth:`Log.use` and cached in :class:`Log`. Not intended
    to be instantiated directly.

    Parameters
    ----------
    log : Log
        Parent logger.
    log_kind : LogKind
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
        self: _BoundLog[Literal["success", "sleep"]],
        message: str,
        *args: object,
    ) -> None: ...

    @overload
    def __call__(
        self: _BoundLog[Literal["retry", "failure"]],
        message: str,
        *args: object,
        intercepted_exception: Exception | None,
    ) -> None: ...

    def __call__(
        self,
        message: str,
        *args: object,
        intercepted_exception: Exception | None = None,
    ) -> None:
        """
        Emit a log message using the bound logger kind.

        Parameters
        ----------
        message : str
            ``%``-style format string.
        *args : object
            Format arguments.
        intercepted_exception : Exception | None, optional
            Exception to pass via ``logger_traceback_kwarg`` if traceback
            logging is enabled for the bound kind. Only meaningful for
            ``"retry"`` and ``"failure"``; ignored for ``"sleep"`` and
            ``"success"``.

        """
        self._log.record(
            log_kind=self._log_kind,
            message=message,
            args=args,
            intercepted_exception=intercepted_exception,
        )
