"""Retry decorator for synchronous and asynchronous functions."""

__all__ = (
    "config",
    "retry",
    "retry_async",
)

from fastretry._configs.config import (
    config,
)
from fastretry._decorators.retry import (
    retry,
)
from fastretry._decorators.retry_async import (
    retry_async,
)
from fastretry._metadata.version import (
    __getattr__ as __getattr__,
)
