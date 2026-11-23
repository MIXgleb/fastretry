"""
Validation of the options accepted by the public API.

The decorators take their options through ``**kwargs``, so an unknown or
misplaced name would otherwise surface as a :exc:`TypeError` raised by an
internal class. This module rejects such names up front and points at the
right place to configure them.

Values are validated separately, when a decorator is applied to a callable:
:class:`OptionsValidator` checks the global defaults and the resolved
decorator options, and replaces recoverable mistakes with their fallbacks.
"""

import dataclasses as dc
import difflib
import math
from collections.abc import (
    Mapping,
)
from concurrent.futures import (
    Executor,
)
from typing import (
    Final,
    cast,
    final,
)

from fastretry._compat.sentinels import (
    UnsetType,
)
from fastretry._configs.defaults import (
    Defaults,
)
from fastretry._utils.callbacks import (
    CALLBACK_NAMES,
)
from fastretry._utils.delays import (
    JITTER_STRATEGIES,
    Delay,
    ExponentialDelay,
)
from fastretry._utils.logs import (
    LogLevel,
)
from fastretry._utils.shared_loop import (
    ASYNC_CALLBACK_MODES,
)
from fastretry._utils.stats import (
    DecoratorOptions,
)
from fastretry._utils.warnings import (
    Warnings,
)

RETRY_OPTIONS: Final[frozenset[str]] = frozenset(
    {
        "attempts",
        "callbacks",
        "delay",
        "disable_logging",
        "disable_warnings",
        "jitter",
        "max_time",
        "no_retry_on",
        "retry_on",
        "return_default_value",
    },
)
"""
Options accepted by both :func:`~fastretry.retry` and
:func:`~fastretry.retry_async`.
"""

RETRY_ASYNC_OPTIONS: Final[frozenset[str]] = RETRY_OPTIONS | {"executor"}
"""Options accepted by :func:`~fastretry.retry_async`."""

GLOBAL_RETRY_OPTIONS: Final[frozenset[str]] = frozenset(
    {
        "async_callback_mode",
        "jitter_for_exponential",
        "jitter_for_fixed",
        "on_failure",
        "on_retry",
        "on_success",
        "unwrap_single_exception",
    },
)
"""Retry options that are configurable only through :attr:`~fastretry.config.retry`."""

GLOBAL_LOGGING_OPTIONS: Final[frozenset[str]] = frozenset(
    {
        "install_default_handler",
        "level_failure",
        "level_retry",
        "level_sleep",
        "level_success",
        "traceback_min_level",
    },
)
"""Logging options that are configurable only through :attr:`~fastretry.config.logging`."""

RETRY_DEFAULTS_NAMES: Final[frozenset[str]] = (RETRY_OPTIONS - {"callbacks"}) | GLOBAL_RETRY_OPTIONS
"""Defaults accepted by :attr:`~fastretry.config.retry`."""

LOGGING_DEFAULTS_NAMES: Final[frozenset[str]] = GLOBAL_LOGGING_OPTIONS
"""Defaults accepted by :attr:`~fastretry.config.logging`."""

_GLOBAL_SCOPES: Final[dict[str, str]] = {
    **dict.fromkeys(sorted(GLOBAL_RETRY_OPTIONS), "config.retry(...)"),
    **dict.fromkeys(sorted(GLOBAL_LOGGING_OPTIONS), "config.logging(...)"),
}
"""Settings entry point for every option that cannot be passed to a decorator."""

_KNOWN_OPTIONS: Final[tuple[str, ...]] = tuple(
    sorted(RETRY_OPTIONS | RETRY_ASYNC_OPTIONS | GLOBAL_RETRY_OPTIONS | GLOBAL_LOGGING_OPTIONS),
)
"""Every option name a user may have meant, used for suggestions."""


def validate_decorator_kwargs(
    *,
    kwargs: Mapping[str, object],
    decorator_name: str,
    allow_executor: bool = False,
) -> None:
    """
    Reject keyword arguments that a decorator cannot accept.

    Parameters
    ----------
    kwargs : Mapping[str, object]
        Keyword arguments passed to the decorator.
    decorator_name : str
        Decorator name used in error messages, e.g. ``"retry"``.
    allow_executor : bool, ``optional``
        Whether the ``executor`` option is accepted, by default False.

    Raises
    ------
    TypeError
        If a keyword argument is unknown, is configurable only globally,
        or is not supported by this decorator.

    """
    if not kwargs:
        return

    allowed = RETRY_ASYNC_OPTIONS if allow_executor else RETRY_OPTIONS

    for name in kwargs:
        if name in allowed:
            continue

        scope = _GLOBAL_SCOPES.get(name)

        if scope is not None:
            msg = f"`{name}` is a global option, configure it via `{scope}`"
            raise TypeError(msg)

        if name == "executor":
            msg = "`executor` is only supported by `retry_async(...)`"
            raise TypeError(msg)

        msg = f"{decorator_name}() got an unexpected keyword argument {name!r}"
        suggestion = difflib.get_close_matches(name, _KNOWN_OPTIONS, n=1)

        if suggestion:
            match = suggestion[0]
            scope = _GLOBAL_SCOPES.get(match)

            if scope is None:
                msg = f"{msg}; did you mean `{match}`?"
            else:
                msg = f"{msg}; did you mean the global option `{match}` from `{scope}`?"

        raise TypeError(msg)


@final
class OptionsValidator:
    """
    Validate the options of a retry decorator and of the global defaults.

    Recoverable mistakes are reported through
    :class:`~fastretry._utils.warnings.Warnings` and replaced with a
    fallback, so a decorator that was created successfully can be used as
    is. Mistakes that cannot be fixed raise :exc:`TypeError` or
    :exc:`ValueError`.

    Parameters
    ----------
    warnings : Warnings
        Warning emitter that respects the ``disable_warnings`` flag.

    """

    __slots__ = ("_warnings",)

    def __init__(
        self,
        *,
        warnings: Warnings,
    ) -> None:
        self._warnings = warnings

    def validate_decorator_options(
        self,
        *,
        options: DecoratorOptions,
        callbacks: object,
    ) -> DecoratorOptions:
        """
        Validate everything a decorator resolved before its first attempt.

        Parameters
        ----------
        options : DecoratorOptions
            Options resolved for this decorator, including the derived
            jitter strategy.
        callbacks : object
            Callback mapping passed to the decorator, ``UNSET`` to use only
            the defaults, or ``None`` to disable every callback.

        Returns
        -------
        DecoratorOptions
            Copy of ``options`` with recoverable mistakes replaced by their
            fallbacks: ``attempts`` below 1 becomes 1, and a negative fixed
            ``delay`` becomes 0.

        Notes
        -----
        Application-wide and logging defaults are validated by
        :meth:`validate_defaults_options`, which runs before this method.
        The defaults of the per-decorator values are validated here, as
        resolved options, so each of them is checked exactly once.

        Values that cannot be fixed raise :exc:`TypeError` when they are of
        the wrong type, and :exc:`ValueError` when they are out of range or
        name an unknown strategy.

        """
        attempts = self._validate_attempts(attempts=options.attempts)
        delay = self._validate_delay(delay=options.delay)
        max_time = self._validate_max_time(max_time=options.max_time)

        self._validate_selection(
            values={"jitter": options.jitter},
            allowed=JITTER_STRATEGIES,
        )
        self._validate_booleans(
            values={
                "disable_logging": options.disable_logging,
                "disable_warnings": options.disable_warnings,
            },
        )
        self._validate_exception_types(
            values={
                "retry_on": options.retry_on,
                "no_retry_on": options.no_retry_on,
            },
        )
        self._validate_callbacks(callbacks=callbacks)
        self._validate_executor(executor=options.executor)

        return dc.replace(
            options,
            attempts=attempts,
            delay=delay,
            max_time=max_time,
        )

    def validate_defaults_options(
        self,
        *,
        defaults: Defaults,
    ) -> None:
        """
        Validate every value configured through the ``config`` entry point.

        Checked when a decorator is created, because the defaults are
        resolved into it. Values that also exist per decorator are validated
        as resolved options in :meth:`validate_decorator_options`; this
        method covers the application-wide and logging settings that never
        reach a decorator argument.

        Parameters
        ----------
        defaults : Defaults
            Defaults resolved for the decorator, validated together with its
            options.

        Notes
        -----
        A default of the wrong type raises :exc:`TypeError`; a default that
        is out of range raises :exc:`ValueError`.

        """
        self._validate_callables(
            values={
                "on_success": defaults.on_success,
                "on_retry": defaults.on_retry,
                "on_failure": defaults.on_failure,
            },
        )
        self._validate_selection(
            values={
                "jitter_for_exponential": defaults.jitter_for_exponential,
                "jitter_for_fixed": defaults.jitter_for_fixed,
            },
            allowed=JITTER_STRATEGIES,
        )
        self._validate_selection(
            values={"async_callback_mode": defaults.async_callback_mode},
            allowed=ASYNC_CALLBACK_MODES,
        )
        self._validate_booleans(
            values={
                "install_default_handler": defaults.install_default_handler,
                "unwrap_single_exception": defaults.unwrap_single_exception,
            },
        )
        self._validate_log_levels(
            values={
                "level_success": defaults.level_success,
                "level_retry": defaults.level_retry,
                "level_failure": defaults.level_failure,
                "level_sleep": defaults.level_sleep,
                "traceback_min_level": defaults.traceback_min_level,
            },
        )

    def _validate_attempts(
        self,
        *,
        attempts: object,
    ) -> int:
        """
        Validate the number of attempts.

        A value below 1 is replaced with 1 and reported with a
        :exc:`UserWarning`, so the callable is still invoked once.

        Parameters
        ----------
        attempts : int
            Configured number of attempts.

        Returns
        -------
        int
            Number of attempts to use, never below 1.

        Raises
        ------
        TypeError
            If ``attempts`` is not an :class:`int`. A :class:`bool` is
            rejected even though it is an :class:`int` subclass, because
            ``attempts=True`` says nothing about the number of attempts.

        """
        if isinstance(attempts, bool) or not isinstance(attempts, int):
            msg = f"attempts must be an int, got {type(attempts).__name__}"
            raise TypeError(msg)

        if attempts < 1:
            self._warnings.warn(
                f"\n\tNumber of attempts must be >= 1, got {attempts!r}. Falling back to 1.",
                stacklevel=7,
            )
            return 1

        return attempts

    def _validate_delay(
        self,
        *,
        delay: object,
    ) -> Delay:
        """
        Validate the delay configuration.

        A custom delay callable can only be validated when it is called.
        A negative fixed delay is replaced with 0 and reported with a
        :exc:`UserWarning`.

        Parameters
        ----------
        delay : Delay
            Configured delay.

        Returns
        -------
        Delay
            Delay to use, with a negative fixed delay replaced by 0.

        Raises
        ------
        TypeError
            If ``delay`` is neither a number, an
            :class:`~fastretry.delays.ExponentialDelay` nor a callable.
        ValueError
            If a fixed delay is not a finite number of seconds.

        Notes
        -----
        Parameters of an :class:`~fastretry.delays.ExponentialDelay` are
        checked by :meth:`_validate_exponential_delay`; an out-of-range value
        raises :exc:`ValueError` there.

        """
        if isinstance(delay, ExponentialDelay):
            self._validate_exponential_delay(delay=delay)
            return delay

        if isinstance(delay, bool):
            msg = "delay must be a number of seconds, an ExponentialDelay or a callable, got bool"
            raise TypeError(msg)

        if isinstance(delay, (int, float)):
            if not math.isfinite(delay):
                msg = f"delay must be a finite number of seconds, got {delay!r}"
                raise ValueError(msg)

            if delay < 0:
                self._warnings.warn(
                    f"\n\tDelay must be >= 0, got {delay!r}. Falling back to 0.",
                    stacklevel=7,
                )
                return 0

            return delay

        if callable(delay):
            return delay  # pyright: ignore[reportReturnType]

        msg = (
            "delay must be a number of seconds, an ExponentialDelay or a callable, "
            f"got {type(delay).__name__}"
        )
        raise TypeError(msg)

    @staticmethod
    def _validate_max_time(
        *,
        max_time: object,
    ) -> float | None:
        """
        Validate the time budget of a call.

        Parameters
        ----------
        max_time : float | None
            Configured time budget in seconds, or ``None`` for no budget.

        Returns
        -------
        float | None
            Budget to use, normalized to a :class:`float`.

        Raises
        ------
        TypeError
            If ``max_time`` is neither a number nor ``None``.
        ValueError
            If ``max_time`` is not a finite positive number of seconds.

        """
        if max_time is None:
            return None

        if isinstance(max_time, bool) or not isinstance(max_time, (int, float)):
            msg = f"max_time must be a number of seconds or None, got {type(max_time).__name__}"
            raise TypeError(msg)

        if not math.isfinite(max_time):
            msg = f"max_time must be finite, got {max_time!r}"
            raise ValueError(msg)

        if max_time <= 0:
            msg = f"max_time must be > 0, got {max_time!r}"
            raise ValueError(msg)

        return float(max_time)

    @staticmethod
    def _validate_exponential_delay(
        *,
        delay: ExponentialDelay,
    ) -> None:
        """
        Validate the parameters of an exponential backoff.

        Parameters
        ----------
        delay : ExponentialDelay
            Exponential backoff configuration.

        Raises
        ------
        TypeError
            If a parameter is not a number.
        ValueError
            If a parameter is out of range or not finite.

        """
        for name, value in (
            ("delay", delay.delay),
            ("backoff factor", delay.backoff_factor),
            ("maximum delay", delay.max_delay),
        ):
            if value is None:
                continue

            if isinstance(value, bool) or not isinstance(value, (int, float)):
                msg = f"{name} must be a number, got {type(value).__name__}"
                raise TypeError(msg)

            if not math.isfinite(value):
                msg = f"{name} must be finite, got {value!r}"
                raise ValueError(msg)

        if delay.delay <= 0:
            msg = f"delay must be > 0, got {delay.delay!r}"
            raise ValueError(msg)

        if delay.backoff_factor <= 0:
            msg = f"backoff factor must be > 0, got {delay.backoff_factor!r}"
            raise ValueError(msg)

        if delay.max_delay is None:
            return

        if delay.max_delay <= 0:
            msg = f"maximum delay must be > 0, got {delay.max_delay!r}"
            raise ValueError(msg)

        if delay.max_delay < delay.delay:
            msg = f"maximum delay ({delay.max_delay!r}) must be >= base delay ({delay.delay!r})"
            raise ValueError(msg)

    @staticmethod
    def _validate_booleans(
        *,
        values: Mapping[str, object],
    ) -> None:
        """
        Validate that every value is a :class:`bool`.

        Parameters
        ----------
        values : Mapping[str, object]
            Option names mapped to their values.

        Raises
        ------
        TypeError
            If a value is not a :class:`bool`.

        """
        for name, value in values.items():
            if not isinstance(value, bool):
                msg = f"{name} must be a bool, got {type(value).__name__}"
                raise TypeError(msg)

    @staticmethod
    def _validate_exception_types(
        *,
        values: Mapping[str, object],
    ) -> None:
        """
        Validate that every value is an exception class or a tuple of them.

        Parameters
        ----------
        values : Mapping[str, object]
            Option names mapped to their values.

        Raises
        ------
        TypeError
            If a value holds something that is not an exception class.

        """
        for name, value in values.items():
            candidates: tuple[object, ...] = value if isinstance(value, tuple) else (value,)  # pyright: ignore[reportUnknownVariableType]

            for candidate in candidates:
                if isinstance(candidate, type) and issubclass(candidate, BaseException):
                    continue

                msg = (
                    f"{name} must be an exception class or a tuple of exception classes, "
                    f"got {candidate!r}"
                )
                raise TypeError(msg)

    @staticmethod
    def _validate_selection(
        *,
        values: Mapping[str, object],
        allowed: frozenset[str],
    ) -> None:
        """
        Validate that every value is one of the ``allowed`` strings.

        Parameters
        ----------
        values : Mapping[str, object]
            Option names mapped to their values.
        allowed : frozenset[str]
            Accepted values.

        Raises
        ------
        ValueError
            If a value is not in ``allowed``.

        """
        expected = ", ".join(map(repr, sorted(allowed)))

        for name, value in values.items():
            if isinstance(value, str) and value in allowed:
                continue

            msg = f"{name} must be one of {expected}, got {value!r}"
            raise ValueError(msg)

    @staticmethod
    def _validate_callables(
        *,
        values: Mapping[str, object],
    ) -> None:
        """
        Validate that every value is callable or ``None``.

        Parameters
        ----------
        values : Mapping[str, object]
            Option names mapped to their values.

        Raises
        ------
        TypeError
            If a value is neither callable nor ``None``.

        """
        for name, value in values.items():
            if value is None or callable(value):
                continue

            msg = f"{name} must be callable or None, got {type(value).__name__}"
            raise TypeError(msg)

    @staticmethod
    def _validate_log_levels(
        *,
        values: Mapping[str, object],
    ) -> None:
        """
        Validate that every value is a :class:`~fastretry.logging.LogLevel`.

        Parameters
        ----------
        values : Mapping[str, object]
            Option names mapped to their values.

        Raises
        ------
        TypeError
            If a value is not a :class:`~fastretry.logging.LogLevel`.

        """
        for name, value in values.items():
            if isinstance(value, LogLevel):
                continue

            msg = f"{name} must be a LogLevel, got {type(value).__name__}"
            raise TypeError(msg)

    @staticmethod
    def _validate_callbacks(
        *,
        callbacks: object,
    ) -> None:
        """
        Validate the callback mapping before it is resolved.

        Parameters
        ----------
        callbacks : RetryCallbacks | None, ``optional``
            Mapping passed to the decorator, ``UNSET`` to use only the
            defaults, or ``None`` to disable every callback.

        Raises
        ------
        TypeError
            If ``callbacks`` is not a mapping or holds a non-callable value.
        ValueError
            If the mapping holds an unknown callback name.

        """
        if callbacks is None or isinstance(callbacks, UnsetType):
            return

        if isinstance(callbacks, Mapping):
            callbacks = cast("Mapping[str, object]", callbacks)
            unknown = set(callbacks) - CALLBACK_NAMES

            if unknown:
                names = ", ".join(map(repr, sorted(unknown, key=repr)))
                expected = ", ".join(map(repr, sorted(CALLBACK_NAMES)))
                msg = f"unknown callback name(s): {names}; expected one of {expected}"
                raise ValueError(msg)

            for name, callback in callbacks.items():
                if callback is not None and not callable(callback):
                    msg = (
                        f"callback {name!r} must be callable or None, got {type(callback).__name__}"
                    )
                    raise TypeError(msg)
            return

        msg = f"callbacks must be a mapping, got {type(callbacks).__name__}"
        raise TypeError(msg)

    @staticmethod
    def _validate_executor(
        *,
        executor: object,
    ) -> None:
        """
        Validate the executor.

        Parameters
        ----------
        executor : Executor | None
            Executor used to run sync callables in an async context.

        Raises
        ------
        TypeError
            If ``executor`` is neither ``None`` nor an
            :class:`~concurrent.futures.Executor`.

        """
        if executor is None or isinstance(executor, Executor):
            return

        msg = (
            "executor must be a concurrent.futures.Executor instance or None, "
            f"got {type(executor).__name__}"
        )
        raise TypeError(msg)
