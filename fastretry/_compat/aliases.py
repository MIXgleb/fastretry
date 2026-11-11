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
type CoroType[R] = types.CoroutineType[Any, Any, R]
type WrappedCoro[R] = Coroutine[Any, Any, R | UnsetType]
type RetryOnExceptionType = type[BaseException] | tuple[type[BaseException], ...]
