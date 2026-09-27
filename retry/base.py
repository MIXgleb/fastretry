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
    Final,
    Self,
    final,
)

from retry._defaults import (
    defaults,
)
from retry._types import (
    UNSET,
    Delay,
    ExponentialDelay,
    JitterStrategy,
    UnsetType,
)
from retry._utils import (
    DelayCalculator,
    FunctionTypes,
    Log,
    Warnings,
)


class BaseRetrying[R, WrappedFunc: Callable[..., Any]](ABC):
    """Retrying decorator for multiple attempts to execute a function in case of an error."""

    __slots__ = (
        "_log",
        "_warnings",
        "attempts",
        "delay",
        "disable_logging",
        "disable_warnings",
        "include_traceback_in_failure_log",
        "include_traceback_in_retry_log",
        "jitter",
        "logger_failure",
        "logger_retry",
        "logger_sleep",
        "logger_success",
        "logger_traceback_kwarg",
        "re_raise_exception",
        "return_default_value",
    )

    def __init__(  # ruff: ignore[too-many-arguments]
        self,
        *,
        attempts: int | UnsetType = UNSET,
        return_default_value: R | UnsetType = UNSET,
        delay: Delay | UnsetType = UNSET,
        jitter: JitterStrategy | UnsetType = UNSET,
        disable_logging: bool | UnsetType = UNSET,
        disable_warnings: bool | UnsetType = UNSET,
    ) -> None:
        """
        Initialize the retry decorator.

        Parameters
        ----------
        attempts : int, optional
            Number of attempts
        return_default_value : Any, optional
            Default value returned if the function fails after all attempts,
        delay : Delay, optional
            Delay between attempts in seconds. May be a plain ``float`` for a
            fixed delay or an :class:`~._utils._delay.ExponentialDelay` for
            exponential backoff.
        jitter : JitterStrategy, optional
            Jitter strategy overriding the default for the given delay type.
            When omitted, ``jitter_for_exponential`` or ``jitter_for_fixed``
            from the global defaults is used.
        disable_logging : bool, optional
            Disable all logging
        disable_warnings : bool, optional
            Disable all warnings

        """
        # --- per-decorator options ---
        self.return_default_value: Final = self._resolve(
            passed=return_default_value,
            default=UNSET,
        )
        self.attempts: Final = self._resolve(
            passed=attempts,
            default=defaults.attempts,
        )
        self.delay: Final = self._resolve(
            passed=delay,
            default=defaults.delay,
        )
        self.disable_logging: Final = self._resolve(
            passed=disable_logging,
            default=defaults.disable_logging,
        )
        self.disable_warnings: Final = self._resolve(
            passed=disable_warnings,
            default=defaults.disable_warnings,
        )

        # --- application-wide options ---
        self.include_traceback_in_retry_log: Final = defaults.include_traceback_in_retry_log
        self.include_traceback_in_failure_log: Final = defaults.include_traceback_in_failure_log

        # --- logger configuration ---
        self.logger_success: Final = defaults.logger_success
        self.logger_retry: Final = defaults.logger_retry
        self.logger_failure: Final = defaults.logger_failure
        self.logger_sleep: Final = defaults.logger_sleep
        self.logger_traceback_kwarg: Final = defaults.logger_traceback_kwarg

        # --- internal helpers ---
        self._log = Log(self)
        self._warnings = Warnings(disable_warnings=self.disable_warnings)

        # --- derived options ---
        self.jitter: Final = self._derive_jitter(jitter=jitter)
        self.re_raise_exception: Final = self._derive_re_raise_exception()

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

    @final
    def wraps(
        self,
        func: WrappedFunc,
    ) -> WrappedFunc:
        """
        Wrap a function with retry logic.

        Performs shared pre-checks and delegates the actual wrapping to
        :meth:`_wrap`. Only ``Exception`` subclasses are retried; all
        ``BaseException`` subclasses (such as ``KeyboardInterrupt``,
        ``SystemExit``, and ``asycnio.CancelError``) propagate immediately.

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
            FunctionTypes(func).warn_on_return_default_mismatch(
                return_default_value=self.return_default_value,
                disable_warnings=self.disable_warnings,
            )

        return self._wrap(func)

    def exception_block(
        self,
        *,
        fname: str,
        retry_index: int,
        intercepted_exception: Exception,
    ) -> None:
        """
        Block is called after one failed attempt.

        Parameters
        ----------
        fname : str
            name of the called function
        retry_index : int
            attempt index
        intercepted_exception : Exception
            intercepted exception during function call

        """
        self._log.record(
            log_kind="retry",
            message="Error executing the '%s' function. Try %d of %d.",
            args=(fname, retry_index, self.attempts),
            intercepted_exception=intercepted_exception,
        )

    def failed_block(
        self,
        *,
        fname: str,
        intercepted_exception: Exception | None,
    ) -> None:
        """
        Block is called after all failed attempts.

        Parameters
        ----------
        fname : str
            name of the called function
        intercepted_exception : Exception | None
            intercepted exception during function call

        """
        self._log.record(
            log_kind="failure",
            message="Failed the execution of the '%s' function.",
            args=(fname,),
            intercepted_exception=intercepted_exception,
        )

        if self.re_raise_exception and intercepted_exception is not None:
            raise intercepted_exception

    @abstractmethod
    def sleep_block(
        self,
        *,
        fname: str,
        retry_index: int,
        delay_calculator: DelayCalculator,
    ) -> Awaitable[None] | None:
        """
        Sleep between attempts.

        Does nothing on the last attempt. The delay is computed by
        ``delay_calculator`` using the configured delay and jitter strategy.

        Parameters
        ----------
        delay_calculator : DelayCalculator
            Delay calculator tracking the previous attempt's delay.
        fname : str
            Name of the wrapped function, used for logging.
        retry_index : int
            Current attempt index (1-based).

        """
        raise NotImplementedError

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

    def _derive_re_raise_exception(self) -> bool:
        """
        Compute ``re_raise_exception`` from ``return_default_value``.

        The two options are mutually exclusive: a wrapper either returns a
        value on failure or re-raises the last exception.

        - If ``return_default_value`` is provided, ``re_raise_exception`` is
        ``False``: the wrapper returns the default value after all attempts
        fail.
        - If ``return_default_value`` is not provided, ``re_raise_exception``
        is ``True``: the wrapper re-raises the last exception.

        Returns
        -------
        bool
            ``True`` when the wrapper should re-raise the last exception,
            ``False`` when it should return ``return_default_value``.

        """
        return isinstance(self.return_default_value, UnsetType)

    def _derive_jitter(
        self,
        *,
        jitter: JitterStrategy | UnsetType,
    ) -> JitterStrategy:
        """
        Resolve the jitter strategy after initialization.

        If ``jitter`` is not provided, the strategy is chosen based on the
        delay type: ``defaults.jitter_for_exponential`` for
        :class:`~._utils._delay.ExponentialDelay`, or
        ``defaults.jitter_for_fixed`` for a plain ``float`` delay.

        Parameters
        ----------
        jitter : JitterStrategy | UnsetType
            Explicit jitter strategy, or ``UNSET`` to fall back to the
            default for the configured delay type.

        Returns
        -------
        JitterStrategy
            Resolved jitter strategy.

        """
        if not isinstance(jitter, UnsetType):
            return jitter

        if isinstance(self.delay, ExponentialDelay):
            return defaults.jitter_for_exponential
        return defaults.jitter_for_fixed

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
