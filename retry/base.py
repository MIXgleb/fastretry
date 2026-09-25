"""
Abstract base class for retry decorators.

``BaseRetrying`` holds the shared state (attempts, delay, logging flags)
and the shared blocks (``exception_block``, ``failed_block``,
``copy``). Concrete sync and async implementations live in
:mod:`~.sync_retry` and :mod:`~.async_retry`.
"""

import copy
import warnings
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
from ._return_type_check import (
    ReturnTypeChecker,
)
from ._types import (
    UNSET,
    UnsetType,
)


class BaseRetrying[R, WrappedFunc: Callable[..., Any]](ABC):
    """Retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = (
        "attempts",
        "delay",
        "disable_error_logging",
        "disable_info_logging",
        "disable_logging",
        "disable_warning_logging",
        "disable_warnings",
        "exc_info_kwarg",
        "include_traceback_in_error_log",
        "include_traceback_in_warning_log",
        "logger_error",
        "logger_info",
        "logger_warning",
        "re_raise_exception",
        "return_default_value",
    )

    def __init__(  # ruff: ignore[too-many-arguments]
        self,
        *,
        attempts: int | UnsetType = UNSET,
        return_default_value: R | UnsetType = UNSET,
        delay: float | UnsetType = UNSET,
        disable_logging: bool | UnsetType = UNSET,
        disable_warnings: bool | UnsetType = UNSET,
        re_raise_exception: bool | UnsetType = UNSET,
    ) -> None:
        """
        Initialize the retry decorator.

        Parameters
        ----------
        attempts : int, optional
            Number of attempts
        return_default_value : Any, optional
            Default value returned if the function fails after all attempts,
        delay : float, optional
            Delay between attempts in seconds
        disable_logging : bool, optional
            Disable all logging
        disable_warnings : bool, optional
            Disable all warnings
        re_raise_exception : bool, optional
            Re-raise an exception after all attempts

        """
        self.return_default_value = return_default_value
        self.attempts = self._resolve(
            passed=attempts,
            default=defaults.attempts,
        )
        self.delay = self._resolve(
            passed=delay,
            default=defaults.delay,
        )
        self.disable_logging = self._resolve(
            passed=disable_logging,
            default=defaults.disable_logging,
        )
        self.disable_warnings = self._resolve(
            passed=disable_warnings,
            default=defaults.disable_warnings,
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

        self.re_raise_exception = self._resolve_re_raise_exception(
            re_raise_exception=re_raise_exception,
        )

    def _resolve_re_raise_exception(
        self,
        *,
        re_raise_exception: bool | UnsetType,
    ) -> bool:
        """
        Resolve ``re_raise_exception`` after initialization.

        The ``return_default_value`` and ``re_raise_exception=True`` options are
        mutually exclusive: a wrapper either returns a value on failure or
        re-raises the last exception.

        - If ``return_default_value`` is provided, the wrapper returns it after
          all attempts fail. ``re_raise_exception=True`` in this case is ignored.
        - If ``return_default_value`` is not provided, the wrapper re-raises the
          last exception by default. ``re_raise_exception=False`` in this case
          causes ``UNSET`` to be returned.

        Returns
        -------
        bool
            re_raise_exception value

        """
        if isinstance(self.return_default_value, UnsetType):
            if re_raise_exception is False:
                if not self.disable_warnings:
                    warnings.warn(
                        "\n\tre_raise_exception=False is set but return_default_value "
                        "is not provided; the wrapper will return `UNSET` by default.\n\t"
                        "Set return_default_value to return a specific value, or set "
                        "re_raise_exception=True to re-raise the last exception.",
                        stacklevel=7,
                    )
                return False
            return True

        if re_raise_exception is True and not self.disable_warnings:
            warnings.warn(
                "\n\tre_raise_exception=True is ignored because return_default_value "
                "is set; the wrapper will return the default value on failure.",
                stacklevel=7,
            )
        return False

    @staticmethod
    def _resolve[T](
        *,
        passed: T | UnsetType,
        default: T,
    ) -> T:
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
            not self.disable_logging
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
            not self.disable_logging
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

    @final
    def wraps(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Wrap a function with retry logic.

        Performs shared pre-checks and delegates the actual
        wrapping to :meth:`_wrap`.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to wrap

        Returns
        -------
        Callable[..., Any]
            Wrapped function with the same signature

        """
        if not isinstance(self.return_default_value, UnsetType):
            ReturnTypeChecker(func).warn_on_return_default_mismatch(
                default_value=self.return_default_value,
            )

        return self._wrap(func)

    @abstractmethod
    def _wrap(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Implement the wrapping logic for a concrete retry strategy.

        Called by :meth:`wraps` after shared pre-checks.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to wrap

        Returns
        -------
        Callable[..., Any]
            Wrapped function with the same signature

        """
        raise NotImplementedError

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
        raise NotImplementedError
