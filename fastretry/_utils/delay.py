"""Delay computation for retry attempts."""

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
    backoff_factor : float, ``optional``
        Multiplier applied on each subsequent attempt, by default 2.0.
        Values ``<= 1.0`` effectively disable exponential growth.
    max_delay : float | None, ``optional``
        Upper bound for the computed delay, by default None (no cap).
        Must be positive when set.

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
        Base delay configuration.
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
        :class:`~retry._utils._delay.ExponentialDelay`, the base grows
        by ``backoff_factor`` on each subsequent attempt and is capped
        at ``max_delay``.

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
        if (
            isinstance(self._delay, ExponentialDelay) and self._delay.delay == 0
        ) or self._delay == 0:
            return 0

        computed = self._apply_backoff(retry_index)
        return self._apply_jitter(computed, previous_delay)

    def _apply_backoff(
        self,
        retry_index: int,
    ) -> float:
        if not isinstance(self._delay, ExponentialDelay):
            return self._delay

        computed = self._delay.delay * (self._delay.backoff_factor ** (retry_index - 1))

        if self._delay.max_delay is not None:
            computed = min(computed, self._delay.max_delay)
        return computed

    def _apply_jitter(
        self,
        computed: float,
        previous_delay: float | None,
    ) -> float:
        match self._jitter:
            case "none":
                return computed
            case "full":
                return self.__calculate_full_jitter(computed)
            case "equal":
                return self.__calculate_equal_jitter(computed)
            case "decorrelated":
                return self.__calculate_decorrelated_jitter(computed, previous_delay)
            case _:
                assert_never(self._jitter)

    def __calculate_decorrelated_jitter(
        self,
        computed: float,
        previous_delay: float | None,
    ) -> float:
        base = self._delay.delay if isinstance(self._delay, ExponentialDelay) else self._delay
        previous = previous_delay if previous_delay is not None else computed
        upper = max(base, previous * 3)

        if isinstance(self._delay, ExponentialDelay) and self._delay.max_delay is not None:
            upper = min(upper, self._delay.max_delay)
            base = min(base, self._delay.max_delay)

        return random.uniform(base, upper)  # ruff: ignore[suspicious-non-cryptographic-random-usage]

    @staticmethod
    def __calculate_full_jitter(computed: float) -> float:
        return random.uniform(0, computed)  # ruff: ignore[suspicious-non-cryptographic-random-usage]

    @staticmethod
    def __calculate_equal_jitter(computed: float) -> float:
        half = computed / 2
        return half + random.uniform(0, half)  # ruff: ignore[suspicious-non-cryptographic-random-usage]
