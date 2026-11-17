"""
Micro-benchmarks: the per-call cost of fastretry against a plain call.

The script measures the overhead a decorator adds to a successful call, to a
call that is retried once, and to async callables: both the regular ``retry``
(the recommended way for coroutine functions) and ``retry_async`` (a coroutine,
or a sync function run in an executor). When ``tenacity`` and/or ``backoff``
are installed, they are measured with equivalent settings, so the same script
produces the comparison table from the documentation.

Run it with the libraries you want to compare::

    uv run --with tenacity --with backoff python benchmarks/benchmark.py

"""

import asyncio
import gc
import sys
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Final,
)

from fastretry import (
    retry,
    retry_async,
)

_ITERATIONS: Final[int] = 20_000
"""Calls per sample."""

_REPEAT: Final[int] = 5
"""Samples per case; the best sample is reported."""

_EXECUTOR_ITERATIONS: Final[int] = 1_000
"""Awaits per sample for the executor case, which is orders of magnitude slower."""

_ATTEMPTS: Final[int] = 3
"""Attempts configured for every library, so the wrappers are comparable."""

_fastretry_calls: list[int] = [0]
"""Call counter for ``fastretry_one_retry``: odd calls raise, so every other one is retried."""


def measure(
    func: Callable[..., object],
    *,
    iterations: int = _ITERATIONS,
) -> float:
    """
    Measure the per-call time of a callable.

    Parameters
    ----------
    func : Callable
        Callable to measure; it must not need arguments.
    iterations : int, ``optional``
        Calls per sample, by default 20 000.

    Returns
    -------
    float
        Best per-call time in microseconds. The best sample is used instead
        of the mean, because the minimum is the least affected by scheduler
        noise and garbage collection pauses.

    """
    samples: list[float] = []

    for _ in range(_REPEAT):
        _ = gc.collect()
        started_at = time.perf_counter()

        for _ in range(iterations):
            _ = func()

        samples.append((time.perf_counter() - started_at) / iterations * 1e6)

    return min(samples)


async def measure_async(
    func: Callable[..., Awaitable[object]],
    *,
    iterations: int = _ITERATIONS,
) -> float:
    """
    Measure the per-await time of a coroutine function.

    Parameters
    ----------
    func : Callable
        Coroutine function to measure; it must not need arguments.
    iterations : int, ``optional``
        Awaits per sample, by default 20 000.

    Returns
    -------
    float
        Best per-await time in microseconds, see :func:`measure`.

    """
    samples: list[float] = []

    for _ in range(_REPEAT):
        _ = gc.collect()
        started_at = time.perf_counter()

        for _ in range(iterations):
            _ = await func()

        samples.append((time.perf_counter() - started_at) / iterations * 1e6)

    return min(samples)


def plain() -> int:
    return 1


@retry(attempts=_ATTEMPTS, disable_logging=True)
def fastretry_success() -> int:
    return 1


@retry(attempts=2, disable_logging=True)
def fastretry_one_retry() -> int:
    _fastretry_calls[0] += 1

    if _fastretry_calls[0] % 2:
        msg = "retry me"
        raise ValueError(msg)

    return 1


async def async_plain() -> int:
    return 1


@retry(attempts=_ATTEMPTS, disable_logging=True)
async def fastretry_coroutine() -> int:
    return 1


@retry_async(attempts=_ATTEMPTS, disable_logging=True)
async def fastretry_async_coroutine() -> int:
    return 1


@retry_async(attempts=_ATTEMPTS, disable_logging=True)
def fastretry_sync_in_executor() -> int:
    return 1


def _tenacity_cases() -> dict[str, Callable[..., object]]:
    """
    Build the tenacity cases, if tenacity is installed.

    Returns
    -------
    dict[str, Callable]
        Cases keyed by display name; empty when tenacity is missing.

    """
    try:
        # pyrefly: ignore[missing-import]
        import tenacity  # pyright: ignore[reportMissingImports] # ruff: ignore[import-outside-top-level]
    except ImportError:
        return {}

    @tenacity.retry(  # type: ignore[untyped-decorator]
        stop=tenacity.stop_after_attempt(_ATTEMPTS),
        wait=tenacity.wait_none(),
        reraise=True,
    )
    def tenacity_success() -> int:
        return 1

    return {"tenacity, success": tenacity_success}


def _backoff_cases() -> dict[str, Callable[..., object]]:
    """
    Build the backoff cases, if backoff is installed.

    Returns
    -------
    dict[str, Callable]
        Cases keyed by display name; empty when backoff is missing.

    """
    try:
        # pyrefly: ignore[missing-import]
        import backoff  # pyright: ignore[reportMissingImports] # ruff: ignore[import-outside-top-level]
    except ImportError:
        return {}

    @backoff.on_exception(  # type: ignore[untyped-decorator]
        backoff.constant,
        ValueError,
        max_tries=_ATTEMPTS,
        jitter=None,
    )
    def backoff_success() -> int:
        return 1

    return {"backoff, success": backoff_success}


def main() -> None:
    """Run every case and print Markdown tables."""
    cases: dict[str, Callable[..., object]] = {
        "plain call": plain,
        "fastretry, success": fastretry_success,
        "fastretry, one retry": fastretry_one_retry,
        **_tenacity_cases(),
        **_backoff_cases(),
    }

    baseline = measure(cases.pop("plain call"))

    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    print()
    print("| Case | us per call | vs plain |")
    print("|---|---:|---:|")
    print(f"| plain call | {baseline:.2f} | 1.0x |")

    for name, case in cases.items():
        microseconds = measure(case)
        ratio = microseconds / baseline
        print(f"| {name} | {microseconds:.2f} | {ratio:.1f}x |")

    async_baseline = asyncio.run(measure_async(async_plain))

    async_cases: dict[str, tuple[Callable[..., Awaitable[object]], int]] = {
        "retry over a coroutine": (fastretry_coroutine, _ITERATIONS),
        "retry_async over a coroutine": (fastretry_async_coroutine, _ITERATIONS),
        "retry_async over a sync function": (fastretry_sync_in_executor, _EXECUTOR_ITERATIONS),
    }

    print()
    print("| Async case | us per await | vs plain |")
    print("|---|---:|---:|")
    print(f"| plain await | {async_baseline:.2f} | 1.0x |")

    for name, (case, iterations) in async_cases.items():
        microseconds = asyncio.run(measure_async(case, iterations=iterations))
        ratio = microseconds / async_baseline
        print(f"| {name} | {microseconds:.2f} | {ratio:.1f}x |")


if __name__ == "__main__":
    main()
