"""
Abstract base class for retry decorators.

``BaseRetrying`` holds the shared state (attempts, delay, logging flags)
and the shared blocks (``exception_block``, ``failed_block``,
``copy``). Concrete sync and async implementations live in
:mod:`~.sync_retry` and :mod:`~.async_retry`.
"""

import copy
from abc import (
    ABC,
    abstractmethod,
)
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Any,
    Self,
    final,
)

from ._defaults import (
    defaults,
)
from ._types import (
    UNSET,
    UnsetType,
)


class BaseRetrying[ReturnType, WrappedFunc: Callable[..., Any]](ABC):
    """Retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = (
        "attempts",
        "delay",
        "disable_all_logging",
        "disable_error_logging",
        "disable_info_logging",
        "disable_warning_logging",
        "exc_info_kwarg",
        "include_traceback_in_error_log",
        "include_traceback_in_warning_log",
        "logger_error",
        "logger_info",
        "logger_warning",
        "re_raise_exception",
        "return_default_value",
    )

    def __init__(
        self,
        *,
        attempts: int | UnsetType = UNSET,
        return_default_value: ReturnType | UnsetType = UNSET,
        delay: float | UnsetType = UNSET,
        disable_all_logging: bool | UnsetType = UNSET,
        re_raise_exception: bool | UnsetType = UNSET,
    ) -> None:
        """
        Initialize the retry decorator.

        Parameters
        ----------
        attempts : int, optional
            Number of attempts
        return_default_value : ReturnType, optional
            Default value returned if the function fails after all attempts,
        delay : float, optional
            Delay between attempts in seconds
        disable_all_logging : bool, optional
            Disable all logging
        re_raise_exception : bool, optional
            Re-raise an exception after all attempts

        """
        self.attempts = self._resolve(
            passed=attempts,
            default=defaults.attempts,
        )
        self.return_default_value = self._resolve(
            passed=return_default_value,
            default=None,
        )
        self.delay = self._resolve(
            passed=delay,
            default=defaults.delay,
        )
        self.disable_all_logging = self._resolve(
            passed=disable_all_logging,
            default=defaults.disable_all_logging,
        )
        self.re_raise_exception = self._resolve(
            passed=re_raise_exception,
            default=defaults.re_raise_exception,
        )
        self.disable_info_logging = defaults.disable_info_logging
        self.disable_warning_logging = defaults.disable_warning_logging
        self.disable_error_logging = defaults.disable_error_logging
        self.include_traceback_in_warning_log = defaults.include_traceback_in_warning_log
        self.include_traceback_in_error_log = defaults.include_traceback_in_error_log
        self.logger_info = defaults.logger_info
        self.logger_warning = defaults.logger_warning
        self.logger_error = defaults.logger_error
        self.exc_info_kwarg = defaults.exc_info_kwarg

    @staticmethod
    def _resolve[T](passed: T | UnsetType, default: T) -> T:
        """
        Resolve a value by priority: passed > factory default.

        Parameters
        ----------
        passed : T | UnsetType
            passed value
        default: T
            factory default value

        Returns
        -------
        T
            set value

        """
        return passed if not isinstance(passed, UnsetType) else default

    @final
    def copy(self) -> Self:
        """
        Copy this object.

        Returns
        -------
        Self
            copied instance of the class

        """
        return copy.copy(self)

    def exception_block(
        self,
        fname: str,
        retry_index: int,
        intercepted_exception: BaseException,
    ) -> None:
        """
        Block is called after one failed attempt.

        Parameters
        ----------
        fname : str
            name of the called function
        retry_index : int
            attempt index
        intercepted_exception : BaseException
            intercepted exception during function call

        """
        kwargs: dict[str, Any] = {}
        if self.include_traceback_in_warning_log:
            kwargs[self.exc_info_kwarg] = intercepted_exception

        if (
            not self.disable_all_logging
            and not self.disable_warning_logging
            and self.logger_warning is not None
        ):
            self.logger_warning(
                "Error executing the '%s' function. Try %d of %d.",
                fname,
                retry_index,
                self.attempts,
                **kwargs,
            )

    def failed_block(
        self,
        fname: str,
        intercepted_exception: BaseException | None,
    ) -> None:
        """
        Block is called after all failed attempts.

        Parameters
        ----------
        fname : str
            name of the called function
        intercepted_exception : BaseException | None
            intercepted exception during function call

        """
        kwargs: dict[str, Any] = {}
        if self.include_traceback_in_error_log and intercepted_exception is not None:
            kwargs[self.exc_info_kwarg] = intercepted_exception

        if (
            not self.disable_all_logging
            and not self.disable_error_logging
            and self.logger_error is not None
        ):
            self.logger_error(
                "Failed the execution of the '%s' function.",
                fname,
                **kwargs,
            )

        if self.re_raise_exception and intercepted_exception is not None:
            raise intercepted_exception

    @abstractmethod
    def wraps(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Wrap a function with retry logic.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to wrap

        Returns
        -------
        Callable[..., Any]
            Wrapped function with the same signature

        """

    @abstractmethod
    def sleep_block(
        self,
        fname: str,
        retry_index: int,
    ) -> Awaitable[None] | None:
        """
        Sleep between attempts.

        Does nothing if ``delay`` is zero or if this is the last attempt.

        Parameters
        ----------
        fname : str
            Name of the wrapped function, used for logging
        retry_index : int
            Current attempt index (1-based)

        """
