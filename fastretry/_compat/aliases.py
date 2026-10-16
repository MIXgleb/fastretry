"""Shared type aliases."""

import types
from collections.abc import (
    Coroutine,
)
from typing import (
    Any,
)

from retry._compat.sentinels import (
    UnsetType,
)

type CoroType[R] = types.CoroutineType[Any, Any, R]
type WrappedCoroType[R] = Coroutine[Any, Any, R | UnsetType]
type RetryOnExceptionType = type[BaseException] | tuple[type[BaseException], ...]
