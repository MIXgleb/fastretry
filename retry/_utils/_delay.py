"""
Delay computation for retry attempts.

Provides :class:`ExponentialDelay` for configuring exponential backoff and
:class:`DelayCalculator` for computing the effective delay of an attempt,
including jitter.
"""

import random
from typing import (
    Literal,
    NamedTuple,
    assert_never,
)

type Delay = float | ExponentialDelay
type JitterStrategy = Literal["full", "equal", "decorrelated", "none"]


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
    backoff_factor : float, optional
        Multiplier applied on each subsequent attempt, by default 2.0.
        Values ``<= 1.0`` effectively disable exponential growth.
    max_delay : float | None, optional
        Upper bound for the computed delay, by default None (no cap).
        Must be positive when set.

    """

    delay: float
    backoff_factor: float = 2.0
    max_delay: float | None = None


class DelayCalculator:
    """
    Compute effective delays for retry attempts, with jitter.

    Stateful: tracks the delay used on the previous attempt, which is
    required by the ``"decorrelated"`` jitter strategy. Each retry loop
    should use its own instance.

    Parameters
    ----------
    delay : Delay
        Base delay configuration.
    jitter : JitterStrategy
        Jitter strategy to apply.

    """

    __slots__ = (
        "_delay",
        "_jitter",
        "_previous_delay",
    )

    def __init__(
        self,
        *,
        delay: Delay,
        jitter: JitterStrategy,
    ) -> None:
        self._delay = delay
        self._jitter: JitterStrategy = jitter
        self._previous_delay: float | None = None

    def compute(
        self,
        retry_index: int,
    ) -> float:
        """
        Compute the effective delay for a retry attempt.

        For a plain ``float`` delay, the base value is used as-is. For an
        :class:`ExponentialDelay`, the base grows by ``backoff_factor``
        on each subsequent attempt and is capped at ``max_delay``.

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

        Returns
        -------
        float
            Effective delay in seconds.

        """
        computed = self._apply_backoff(retry_index)
        result = self._apply_jitter(computed)
        self._previous_delay = result
        return result

    def _apply_backoff(
        self,
        retry_index: int,
    ) -> float:
        """
        Compute the base delay with exponential backoff and cap.

        Parameters
        ----------
        retry_index : int
            1-based attempt index.

        Returns
        -------
        float
            Delay before jitter.

        """
        if not isinstance(self._delay, ExponentialDelay):
            return self._delay

        computed = self._delay.delay * (self._delay.backoff_factor ** (retry_index - 1))

        if self._delay.max_delay is not None:
            computed = min(computed, self._delay.max_delay)
        return computed

    def _apply_jitter(
        self,
        computed: float,
    ) -> float:
        """
        Apply the jitter strategy to the computed delay.

        Parameters
        ----------
        computed : float
            Delay before jitter.

        Returns
        -------
        float
            Delay after jitter.

        """
        match self._jitter:
            case "none":
                return computed
            case "full":
                return random.uniform(0, computed)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            case "equal":
                half = computed / 2
                return half + random.uniform(0, half)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            case "decorrelated":
                base = (
                    self._delay.delay if isinstance(self._delay, ExponentialDelay) else self._delay
                )

                if self._previous_delay is None:
                    return random.uniform(0, computed)  # ruff: ignore[suspicious-non-cryptographic-random-usage]

                upper = self._previous_delay * 3

                if upper <= base:
                    return base
                return random.uniform(base, upper)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            case _:
                assert_never(self._jitter)
