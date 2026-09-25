"""
Logging utilities for retry decorators.

Provides :func:`log` — a level-aware helper that centralizes logger
selection, traceback handling, and signature validation.
"""

import inspect
from typing import (
    TYPE_CHECKING,
    Literal,
    Protocol,
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


class _LogContext(Protocol):
    """
    Interface for objects that expose logging configuration.

    Implemented by ``BaseRetrying``. Any object with these attributes can
    be passed to :func:`log`.
    """

    logger_info: LoggerType | None
    logger_warning: LoggerType | None
    logger_error: LoggerType | None
    exc_info_kwarg: str
    disable_logging: bool
    disable_info_logging: bool
    disable_warning_logging: bool
    disable_error_logging: bool
    include_traceback_in_warning_log: bool
    include_traceback_in_error_log: bool
    disable_warnings: bool


def _resolve(
    ctx: _LogContext,
    level: _LogLevel,
) -> tuple[LoggerType | None, bool, bool]:
    """
    Return the logger, disable flag, and traceback flag for a level.

    Parameters
    ----------
    ctx : LogContext
        Logging configuration.
    level : {"info", "warning", "error"}
        Log level.

    Returns
    -------
    tuple[LoggerType | None, bool, bool]
        Logger, per-level disable flag, and traceback flag.

    """
    if level == "info":
        return ctx.logger_info, ctx.disable_info_logging, False
    if level == "warning":
        return (
            ctx.logger_warning,
            ctx.disable_warning_logging,
            ctx.include_traceback_in_warning_log,
        )
    return (
        ctx.logger_error,
        ctx.disable_error_logging,
        ctx.include_traceback_in_error_log,
    )


def accepts_kwarg(
    func: Callable[..., Any] | None,
    kwarg: str,
) -> bool:
    """
    Check whether ``func`` accepts a keyword argument named ``kwarg``.

    Returns ``True`` if the callable has an explicit keyword parameter,
    a ``**kwargs`` catch-all, or if its signature cannot be inspected
    (built-ins, C extensions). Returns ``False`` only when the signature
    is inspectable and clearly lacks the argument.

    Parameters
    ----------
    func : Callable | None
        Callable to inspect. ``None`` yields ``False``.
    kwarg : str
        Keyword argument name.

    Returns
    -------
    bool
        Whether ``func`` accepts ``kwarg``.

    """
    if func is None:
        return False

    try:
        signature = inspect.signature(func)
    except TypeError, ValueError:
        return True

    for param in signature.parameters.values():
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if param.name == kwarg and param.kind in {
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            return True

    return False


def log(
    ctx: _LogContext,
    *,
    level: _LogLevel,
    message: str,
    args: tuple[Any, ...] = (),
    intercepted_exception: BaseException | None = None,
) -> None:
    """
    Emit a log message at the given level if enabled.

    If traceback logging is enabled for the level but the logger does not
    accept ``ctx.exc_info_kwarg``, a warning is emitted and the message is
    logged without traceback.

    Parameters
    ----------
    ctx : LogContext
        Logging configuration.
    level : {"info", "warning", "error"}
        Log level.
    message : str
        ``%``-style format string.
    args : tuple[Any, ...], optional
        Format arguments.
    intercepted_exception : BaseException | None, optional
        Exception to pass via ``exc_info_kwarg`` if traceback logging is
        enabled for this level.

    """
    kwargs: dict[str, Any] = {}
    logger, disable_level, include_traceback = _resolve(ctx, level)

    if ctx.disable_logging or disable_level or logger is None:
        return

    if include_traceback and intercepted_exception is not None:
        if accepts_kwarg(logger, ctx.exc_info_kwarg):
            kwargs[ctx.exc_info_kwarg] = intercepted_exception
        else:
            warning(
                f"\n\tLogger for level {level!r} does not accept "
                f"{ctx.exc_info_kwarg!r} kwarg; logging without traceback.",
                stacklevel=3,
                disable_warnings=ctx.disable_warnings,
            )

    logger(message, *args, **kwargs)
