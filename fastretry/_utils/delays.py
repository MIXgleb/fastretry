"""Delay computation for retry attempts."""

import math
import random
from collections.abc import (
    Callable,
)
from typing import (
    Literal,
    NamedTuple,
    assert_never,
)

type WaitCallable = Callable[[int, float | None], float]
"""
Custom delay function.

Called with the 1-based index of the failed attempt that is about to be
retried and with the delay used after the previous failed attempt
(``None`` on the first retry, already including jitter). The returned value
is the base delay in seconds; jitter is applied on top of it.

The result must be a finite non-negative number, otherwise
:exc:`ValueError` is raised.
"""

type Delay = float | ExponentialDelay | WaitCallable
"""
Delay between attempts: seconds, an :class:`ExponentialDelay` or a
:data:`WaitCallable`.
"""

type JitterStrategy = Literal["full", "equal", "decorrelated", "none"]
"""
Randomization applied to the computed delay.

- ``"none"`` — the computed delay is used as is.
- ``"full"`` — ``random(0, computed)``.
- ``"equal"`` — ``computed / 2 + random(0, computed / 2)``.
- ``"decorrelated"`` — ``random(base, previous * 3)``, which spreads retries of
  concurrent callers; falls back to ``"full"`` when there is no previous delay.
"""


class ExponentialDelay(NamedTuple):
    """
    Exponential backoff configuration.

    The effective delay for attempt ``n`` (1-based) is::

        delay * backoff_factor ** (n - 1)

    capped at ``max_delay`` when it is set.

    Parameters
    ----------
    delay : float
        Base delay in seconds. Must be positive.
    backoff_factor : float, ``optional``
        Multiplier applied on each subsequent attempt, by default 2.0.
        Values ``<= 1.0`` effectively disable exponential growth.
    max_delay : float | None, ``optional``
        Upper bound for the computed delay, by default None (no cap).
        Must be positive when set.

    Notes
    -----
    Values are validated when a retry decorator using this delay is created,
    not on construction. A non-positive ``delay``, ``backoff_factor``, or
    ``max_delay``, or a ``max_delay`` smaller than ``delay``, raises
    :exc:`ValueError`.

    """

    delay: float
    backoff_factor: float = 2.0
    max_delay: float | None = None


class DelayCalculator:
    """
    Compute effective delays for retry attempts, with jitter.

    Parameters
    ----------
    delay : Delay
        Base delay: seconds, an :class:`ExponentialDelay` or a
        :data:`WaitCallable`.
    jitter : JitterStrategy
        Jitter strategy to apply.

    """

    __slots__ = (
        "_delay",
        "_jitter",
    )

    def __init__(
        self,
        *,
        delay: Delay,
        jitter: JitterStrategy,
    ) -> None:
        self._delay = delay
        self._jitter: JitterStrategy = jitter

    def compute(
        self,
        *,
        retry_index: int,
        previous_delay: float | None = None,
    ) -> float:
        """
        Compute the effective delay for a retry attempt.

        For a plain ``float`` delay, the base value is used as-is. For an
        :class:`~fastretry.delays.ExponentialDelay`, the base grows
        by ``backoff_factor`` on each subsequent attempt and is capped
        at ``max_delay``. For a :data:`~fastretry.delays.WaitCallable`, the
        base is whatever the callable returns for this attempt.

        Jitter is then applied according to the configured strategy:

        - ``"none"``: the computed value is returned as-is.
        - ``"full"``: ``random(0, computed)``.
        - ``"equal"``: ``computed / 2 + random(0, computed / 2)``.
        - ``"decorrelated"``: ``random(base, previous * 3)``, where
          ``base`` is the configured base delay and ``previous`` is the
          delay used on the previous attempt. Falls back to ``"full"``
          when there is no previous delay.

        Parameters
        ----------
        retry_index : int
            1-based attempt index.
        previous_delay : float | None, ``optional``
            Delay used on the previous attempt, by default None. Used by
            the ``"decorrelated"`` jitter strategy; ignored by the others.

        Returns
        -------
        float
            Effective delay in seconds.

        """
        computed = self._apply_backoff(retry_index, previous_delay)

        if computed == 0:
            return 0

        return self._apply_jitter(computed, previous_delay)

    def _apply_backoff(
        self,
        retry_index: int,
        previous_delay: float | None,
    ) -> float:
        delay = self._delay

        if isinstance(delay, ExponentialDelay):
            computed = delay.delay * (delay.backoff_factor ** (retry_index - 1))

            if delay.max_delay is not None:
                computed = min(computed, delay.max_delay)
            return computed

        if callable(delay):
            computed = float(delay(retry_index, previous_delay))

            if not math.isfinite(computed) or computed < 0:
                msg = f"custom delay must return a finite non-negative number, got {computed!r}"
                raise ValueError(msg)
            return computed

        return float(delay)

    def _apply_jitter(
        self,
        computed: float,
        previous_delay: float | None,
    ) -> float:
        jitter = self._jitter

        match jitter:
            case "none":
                return computed
            case "full":
                return self.__calculate_full_jitter(computed)
            case "equal":
                return self.__calculate_equal_jitter(computed)
            case "decorrelated":
                return self.__calculate_decorrelated_jitter(computed, previous_delay)
            case _:
                assert_never(jitter)

    def __calculate_decorrelated_jitter(
        self,
        computed: float,
        previous_delay: float | None,
    ) -> float:
        delay = self._delay
        previous = previous_delay if previous_delay is not None else computed

        if isinstance(delay, ExponentialDelay):
            base = delay.delay
            upper = max(base, previous * 3)

            if delay.max_delay is not None:
                upper = min(upper, delay.max_delay)
                base = min(base, delay.max_delay)
        else:
            base = computed
            upper = max(base, previous * 3)

        return random.uniform(base, upper)  # ruff: ignore[suspicious-non-cryptographic-random-usage]

    @staticmethod
    def __calculate_full_jitter(computed: float) -> float:
        return random.uniform(0, computed)  # ruff: ignore[suspicious-non-cryptographic-random-usage]

    @staticmethod
    def __calculate_equal_jitter(computed: float) -> float:
        half = computed / 2
        return half + random.uniform(0, half)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
