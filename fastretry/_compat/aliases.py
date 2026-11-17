"""Shared type aliases."""

import types
from collections.abc import (
    Coroutine,
)
from typing import (
    Any,
)

from fastretry._compat.sentinels import (
    UnsetType,
)

type Coro[R] = Coroutine[Any, Any, R]
"""Anything that can be awaited with result ``R``, as accepted by the decorators."""

type CoroType[R] = types.CoroutineType[Any, Any, R]
"""Concrete coroutine object, as returned by calling an ``async def`` function."""

type WrappedCoro[R] = Coroutine[Any, Any, R | UnsetType]
"""
Coroutine returned by a wrapper function.

The result is ``R`` when the call succeeded, or the ``UNSET`` sentinel when the
wrapper returned without a value, e.g. because ``return_default_value`` is not
set.
"""

type RetryOnExceptionType = type[BaseException] | tuple[type[BaseException], ...]
"""Exception type, or a tuple of them, accepted by ``retry_on`` and ``no_retry_on``."""
