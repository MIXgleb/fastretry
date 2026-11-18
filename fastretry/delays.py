"""Public facade for delay strategies."""

__all__ = (
    "Delay",
    "ExponentialDelay",
    "WaitCallable",
)

from fastretry._utils.delays import (
    Delay,
    ExponentialDelay,
    WaitCallable,
)
