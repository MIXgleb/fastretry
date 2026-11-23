"""Tests for delay computation."""

from typing import (
    NoReturn,
)
from unittest.mock import (
    MagicMock,
    patch,
)

import pytest

from fastretry._decorators.retry import (
    retry,
)
from fastretry._utils.delays import (
    DelayCalculator,
    ExponentialDelay,
)


def test_defaults() -> None:
    d = ExponentialDelay(delay=1)
    assert d.backoff_factor == 2
    assert d.max_delay is None


def test_custom() -> None:
    d = ExponentialDelay(delay=2, backoff_factor=3, max_delay=10)
    assert d.delay == 2
    assert d.backoff_factor == 3
    assert d.max_delay == 10


@pytest.mark.parametrize(
    ("delay", "cases"),
    [
        (5, [(1, 5), (2, 5), (10, 5)]),
        (ExponentialDelay(delay=1, backoff_factor=2), [(1, 1), (2, 2), (3, 4)]),
        (
            ExponentialDelay(delay=1, backoff_factor=2, max_delay=5),
            [(1, 1), (3, 4), (4, 5), (10, 5)],
        ),
        (ExponentialDelay(delay=5, backoff_factor=1), [(1, 5), (5, 5)]),
    ],
)
def test_compute_no_jitter(
    delay: object,
    cases: list[tuple[int, float]],
) -> None:
    calc = DelayCalculator(delay=delay, jitter="none")

    for retry_index, expected in cases:
        assert calc.compute(retry_index=retry_index) == expected


@pytest.mark.parametrize(
    "delay",
    [0, ExponentialDelay(delay=0)],
)
def test_zero_delay_returns_zero(delay: object) -> None:
    calc = DelayCalculator(delay=delay, jitter="full")
    assert calc.compute(retry_index=1) == 0
    assert calc.compute(retry_index=5) == 0


@patch("fastretry._utils.delays.random.uniform")
def test_full_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 2.5
    calc = DelayCalculator(delay=5, jitter="full")
    assert calc.compute(retry_index=1) == pytest.approx(2.5)
    mock_uniform.assert_called_once_with(0, 5)


@patch("fastretry._utils.delays.random.uniform")
def test_equal_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 1.25
    calc = DelayCalculator(delay=5, jitter="equal")
    assert calc.compute(retry_index=1) == pytest.approx(2.5 + 1.25)


@patch("fastretry._utils.delays.random.uniform")
def test_decorrelated_jitter_first(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 3
    calc = DelayCalculator(delay=5, jitter="decorrelated")
    assert calc.compute(retry_index=1) == 3
    # base = 5, previous = 5 (fallback to computed), upper = max(5, 15) = 15
    mock_uniform.assert_called_once_with(5, 15)


@patch("fastretry._utils.delays.random.uniform")
def test_decorrelated_jitter_subsequent(mock_uniform: MagicMock) -> None:
    mock_uniform.side_effect = [3, 7]
    calc = DelayCalculator(delay=5, jitter="decorrelated")
    first = calc.compute(retry_index=1)
    second = calc.compute(retry_index=2, previous_delay=first)
    # upper = 3 * 3 = 9, base = 5 → random(5, 9)
    assert second == 7
    mock_uniform.assert_called_with(5, 9)


@patch("fastretry._utils.delays.random.uniform")
def test_decorrelated_jitter_exponential_without_max(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 4
    calc = DelayCalculator(delay=ExponentialDelay(delay=2), jitter="decorrelated")

    assert calc.compute(retry_index=1) == 4
    # base = 2, previous = 2 (fallback to computed), upper = max(2, 6) = 6
    mock_uniform.assert_called_once_with(2, 6)


@patch("fastretry._utils.delays.random.uniform")
def test_decorrelated_jitter_upper_leq_base(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 1
    calc = DelayCalculator(delay=10, jitter="decorrelated")
    # previous = 1 → upper = max(10, 3) = 10, base = 10
    assert calc.compute(retry_index=1, previous_delay=1) == 1
    mock_uniform.assert_called_once_with(10, 10)


@patch("fastretry._utils.delays.random.uniform")
def test_decorrelated_with_max_delay(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 3
    calc = DelayCalculator(
        delay=ExponentialDelay(delay=1, max_delay=5),
        jitter="decorrelated",
    )
    result = calc.compute(retry_index=1, previous_delay=10)
    # base = 1, previous = 10, upper = min(max(1, 30), 5) = 5
    # base = min(1, 5) = 1
    mock_uniform.assert_called_once_with(1, 5)
    assert result == 3


def test_incorrect_jitter() -> None:
    calc = DelayCalculator(delay=5, jitter="incorrect")

    with pytest.raises(AssertionError):
        _ = calc.compute(retry_index=1)


def test_custom_wait_callable_no_jitter() -> None:
    def wait(retry_index: int, _previous_delay: float | None) -> float:
        return 0.5 * retry_index

    calc = DelayCalculator(delay=wait, jitter="none")

    assert calc.compute(retry_index=1) == pytest.approx(0.5)
    assert calc.compute(retry_index=4) == pytest.approx(2.0)


def test_custom_wait_callable_receives_arguments() -> None:
    calls: list[tuple[int, float | None]] = []

    def wait(retry_index: int, previous_delay: float | None) -> float:
        calls.append((retry_index, previous_delay))
        return 1.0

    calc = DelayCalculator(delay=wait, jitter="none")
    _ = calc.compute(retry_index=2, previous_delay=3.5)

    assert calls == [(2, 3.5)]


def test_custom_wait_callable_result_is_float() -> None:
    calc = DelayCalculator(delay=lambda retry_index, _previous_delay: retry_index, jitter="none")

    assert isinstance(calc.compute(retry_index=3), float)


@patch("fastretry._utils.delays.random.uniform")
def test_custom_wait_callable_zero_skips_jitter(mock_uniform: MagicMock) -> None:
    calc = DelayCalculator(delay=lambda _retry_index, _previous_delay: 0.0, jitter="full")

    assert calc.compute(retry_index=1) == 0
    mock_uniform.assert_not_called()


@patch("fastretry._utils.delays.random.uniform")
def test_custom_wait_callable_full_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 1.5
    calc = DelayCalculator(delay=lambda _retry_index, _previous_delay: 4.0, jitter="full")

    assert calc.compute(retry_index=1) == pytest.approx(1.5)
    mock_uniform.assert_called_once_with(0, 4.0)


@patch("fastretry._utils.delays.random.uniform")
def test_custom_wait_callable_equal_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 0.5
    calc = DelayCalculator(delay=lambda _retry_index, _previous_delay: 4.0, jitter="equal")

    assert calc.compute(retry_index=1) == pytest.approx(2.5)
    mock_uniform.assert_called_once_with(0, 2.0)


@patch("fastretry._utils.delays.random.uniform")
def test_custom_wait_callable_decorrelated_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 2.5
    calc = DelayCalculator(delay=lambda _retry_index, _previous_delay: 2.0, jitter="decorrelated")

    assert calc.compute(retry_index=2, previous_delay=1.0) == pytest.approx(2.5)
    # base = 2.0, previous = 1.0 → upper = max(2.0, 3.0) = 3.0
    mock_uniform.assert_called_once_with(2.0, 3.0)


@pytest.mark.parametrize("return_value", [-1.0, float("inf"), float("nan")])
def test_custom_wait_callable_invalid_result(return_value: float) -> None:
    calc = DelayCalculator(
        delay=lambda _retry_index, _previous_delay: return_value,
        jitter="none",
    )

    with pytest.raises(ValueError, match="finite non-negative"):
        _ = calc.compute(retry_index=1)


def test_custom_wait_callable_drives_retries() -> None:
    calls: list[tuple[int, float | None]] = []
    computed: list[float] = []

    def wait(retry_index: int, previous_delay: float | None) -> float:
        calls.append((retry_index, previous_delay))
        return 0.0

    @retry(
        attempts=3,
        delay=wait,
        callbacks={"on_retry": lambda stats: computed.append(stats.attempt.computed_delay)},
    )
    def fn() -> NoReturn:
        raise ValueError

    with pytest.RaisesGroup(ValueError, ValueError, ValueError):
        fn()

    assert calls == [(1, None), (2, 0.0)]
    assert computed[:2] == [0.0, 0.0]


def test_exponential_cap_survives_an_exponent_that_overflows() -> None:
    """The power used to raise OverflowError before max_delay was applied."""
    calc = DelayCalculator(
        delay=ExponentialDelay(delay=1.0, backoff_factor=2.0, max_delay=10.0),
        jitter="none",
    )

    assert calc.compute(retry_index=5) == pytest.approx(10.0)
    assert calc.compute(retry_index=2000) == pytest.approx(10.0)
    assert calc.compute(retry_index=100_000) == pytest.approx(10.0)


def test_exponential_without_cap_reports_infinity_instead_of_overflowing() -> None:
    calc = DelayCalculator(delay=ExponentialDelay(delay=1.0), jitter="none")

    assert calc.compute(retry_index=2000) == float("inf")
