"""Option values that used to be accepted and then crashed the retry loop.

A fixed delay of ``nan`` or ``inf``, and an ``ExponentialDelay`` whose fields
are not finite numbers, passed validation and then failed inside the loop
(``time.sleep(nan)`` raises ``ValueError: Invalid value NaN``, ``time.sleep(inf)``
raises ``OverflowError``) or silently disabled the cap
(``max_delay=nan`` never bounds anything, because ``min(computed, nan)``
is ``computed``).
"""

from typing import (
    Literal,
    NoReturn,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry.delays import (
    ExponentialDelay,
)


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_fixed_delay_is_rejected(delay: float) -> None:
    with pytest.raises(ValueError, match="delay must be a finite number of seconds"):
        retry(attempts=2, delay=delay)(lambda: 1)


def test_bool_delay_is_rejected() -> None:
    with pytest.raises(TypeError, match="delay must be a number of seconds"):
        retry(attempts=2, delay=True)(lambda: 1)  # type: ignore[arg-type]


def test_bool_attempts_is_rejected() -> None:
    with pytest.raises(TypeError, match="attempts must be an int, got bool"):
        retry(attempts=True)(lambda: 1)  # type: ignore[arg-type]


def test_finite_delay_still_works() -> None:
    @retry(attempts=1, delay=0.0)
    def fn() -> Literal[1]:
        return 1

    assert fn() == 1


@pytest.mark.parametrize(
    ("delay", "message"),
    [
        (ExponentialDelay(delay=float("nan")), "delay must be finite"),
        (ExponentialDelay(delay=float("inf")), "delay must be finite"),
        (ExponentialDelay(delay=1.0, backoff_factor=float("nan")), "backoff factor must be finite"),
        (ExponentialDelay(delay=1.0, max_delay=float("nan")), "maximum delay must be finite"),
        (ExponentialDelay(delay=1.0, max_delay=float("inf")), "maximum delay must be finite"),
    ],
)
def test_non_finite_exponential_fields_are_rejected(
    delay: ExponentialDelay,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        retry(attempts=3, delay=delay)(lambda: 1)


@pytest.mark.parametrize(
    ("delay", "message"),
    [
        (ExponentialDelay(delay="1"), "delay must be a number, got str"),  # type: ignore[arg-type]
        (ExponentialDelay(delay=True), "delay must be a number, got bool"),  # type: ignore[arg-type]
        (ExponentialDelay(delay=1.0, backoff_factor="2"), "backoff factor must be a number"),
        (ExponentialDelay(delay=1.0, max_delay="5"), "maximum delay must be a number"),
    ],
)
def test_non_numeric_exponential_fields_are_rejected(
    delay: ExponentialDelay,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        retry(attempts=3, delay=delay)(lambda: 1)


def test_nan_max_delay_no_longer_disables_the_cap() -> None:
    with pytest.raises(ValueError, match="maximum delay must be finite"):
        retry(attempts=3, delay=ExponentialDelay(0.01, max_delay=float("nan")))(lambda: 1)


def test_unknown_callback_names_of_mixed_types_raise_value_error() -> None:
    with pytest.raises(ValueError, match="unknown callback name"):
        retry(attempts=2, callbacks={"bogus": None, 1: None})(lambda: 1)  # type: ignore[dict-item]


def test_rejected_options_never_reach_the_call() -> None:
    calls: list[int] = []

    def fn() -> NoReturn:
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError, match="finite"):
        retry(attempts=2, delay=float("nan"))(fn)

    assert calls == []
