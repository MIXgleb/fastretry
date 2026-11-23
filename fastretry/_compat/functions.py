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
    Check whether ``func`` returns a coroutine when called.

    A plain ``async def`` function, a coroutine function wrapped in
    :class:`functools.partial` and an instance of a class whose ``__call__``
    is async are all recognised. A class object is not: calling a class
    builds an instance, whatever its instances do when called.

    Parameters
    ----------
    func : Callable
        Callable to check.

    Returns
    -------
    TypeIs[Callable[..., Coroutine]]
        ``True`` if calling ``func`` produces a coroutine.

    """
    if inspect.iscoroutinefunction(func):
        return True

    if isinstance(func, type):
        return False

    call = getattr(func, "__call__", None)  # noqa: B004  # not every callable is a function

    return inspect.iscoroutinefunction(call)
