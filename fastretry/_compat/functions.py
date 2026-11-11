"""Runtime helpers for inspecting callables."""

import inspect
from collections.abc import (
    Callable,
)
from typing import (
    TypeIs,
)

from fastretry._compat.aliases import (
    Coro,
)


def is_coroutine_function[**P, R](
    func: Callable[P, R] | Callable[P, Coro[R]],
) -> TypeIs[Callable[P, Coro[R]]]:
    """
    Check whether ``func`` is a coroutine function.

    Parameters
    ----------
    func : Callable[P, R] | Callable[P, CoroutineType[Any, Any, R]]
        Callable to check.

    Returns
    -------
    TypeIs[Callable[P, CoroutineType[Any, Any, R]]]
        ``True`` if ``func`` is a coroutine function.

    """
    return inspect.iscoroutinefunction(func)
