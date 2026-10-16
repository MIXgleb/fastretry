"""Tests for delay computation."""

from unittest.mock import (
    MagicMock,
    patch,
)

import pytest

from retry._utils.delay import (
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


@patch("retry._utils.delay.random.uniform")
def test_full_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 2.5
    calc = DelayCalculator(delay=5, jitter="full")
    assert calc.compute(retry_index=1) == pytest.approx(2.5)
    mock_uniform.assert_called_once_with(0, 5)


@patch("retry._utils.delay.random.uniform")
def test_equal_jitter(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 1.25
    calc = DelayCalculator(delay=5, jitter="equal")
    assert calc.compute(retry_index=1) == pytest.approx(2.5 + 1.25)


@patch("retry._utils.delay.random.uniform")
def test_decorrelated_jitter_first(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 3
    calc = DelayCalculator(delay=5, jitter="decorrelated")
    assert calc.compute(retry_index=1) == 3
    # base = 5, previous = 5 (fallback to computed), upper = max(5, 15) = 15
    mock_uniform.assert_called_once_with(5, 15)


@patch("retry._utils.delay.random.uniform")
def test_decorrelated_jitter_subsequent(mock_uniform: MagicMock) -> None:
    mock_uniform.side_effect = [3, 7]
    calc = DelayCalculator(delay=5, jitter="decorrelated")
    first = calc.compute(retry_index=1)
    second = calc.compute(retry_index=2, previous_delay=first)
    # upper = 3 * 3 = 9, base = 5 → random(5, 9)
    assert second == 7
    mock_uniform.assert_called_with(5, 9)


@patch("retry._utils.delay.random.uniform")
def test_decorrelated_jitter_upper_leq_base(mock_uniform: MagicMock) -> None:
    mock_uniform.return_value = 1
    calc = DelayCalculator(delay=10, jitter="decorrelated")
    # previous = 1 → upper = max(10, 3) = 10, base = 10
    assert calc.compute(retry_index=1, previous_delay=1) == 1
    mock_uniform.assert_called_once_with(10, 10)


@patch("retry._utils.delay.random.uniform")
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
