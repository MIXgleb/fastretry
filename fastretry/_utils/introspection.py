"""
Runtime introspection of the retry loop in progress.

Exposes the current retry state via :class:`contextvars.Context`, plus
a global registry that maps a function name to the ids of its active
retry runs.

The registry uses a lock only on free-threaded builds (Python 3.14+
with the GIL disabled). Under the GIL, ``dict`` operations are atomic,
so the lock is a ``nullcontext`` to avoid overhead.
"""

import contextlib
import contextvars
import sys
import threading
from collections.abc import (
    Mapping,
)
from typing import (
    Final,
    Self,
)

from fastretry._compat.sentinels import (
    UNSET,
    UnsetType,
)
from fastretry._utils.stats import (
    RetryStats,
)

_lock = threading.Lock() if not sys._is_gil_enabled() else contextlib.nullcontext()
_current_stats: Final[contextvars.ContextVar[RetryStats | None]] = contextvars.ContextVar(
    "retry_current_stats",
    default=None,
)
_active_runs: dict[str, dict[int, RetryStats]] = {}


def is_retrying(name: str | UnsetType = UNSET) -> bool:
    """
    Check whether a retry loop is active.

    Without an argument, checks the current context. With a function
    name, checks whether any run with that name is active in the process.

    Parameters
    ----------
    name : str | UnsetType, ``optional``
        Function name to check process-wide, by default ``UNSET``.

    Returns
    -------
    bool
        ``True`` if a matching retry loop is active.

    """
    if isinstance(name, UnsetType):
        return _current_stats.get() is not None

    with _lock:
        return _active_runs.get(name) is not None


def get_current_stats() -> RetryStats | None:
    """
    Return the statistics of the retry loop active in the current context.

    The returned instance is the same object that is passed to lifecycle
    callbacks, so its fields reflect the current attempt at the moment of
    the call. Callers should treat it as read-only.

    If nested retry loops are active in the same context, the innermost
    one is returned.

    Returns
    -------
    RetryStats | None
        Current retry statistics, or ``None`` if no retry loop is active.

    """
    return _current_stats.get()


def get_current_run_id() -> int | None:
    """
    Return the run id of the retry loop active in the current context.

    The run id is the identity of the :class:`RetryStats` instance created
    for this call. It is unique for the lifetime of the call and can be
    used with :func:`get_stats_by_run_id` from another task to look up
    the same run.

    Returns
    -------
    int | None
        Run id, or ``None`` if no retry loop is active.

    """
    stats = _current_stats.get()
    return None if stats is None else id(stats)


def get_stats_for(name: str) -> Mapping[int, RetryStats]:
    """
    Return active retry runs for a function name.

    A function may be executed concurrently in several tasks. Each
    execution has its own :class:`RetryStats` instance and its own run id,
    so the result maps run ids to stats. An empty mapping is returned if
    no run with that name is active.

    Parameters
    ----------
    name : str
        Qualified name of the wrapped function, as reported by
        :attr:`~fastretry._utils.stats.AttemptState.fname`.

    Returns
    -------
    Mapping[int, RetryStats]
        Mapping of run id to :class:`RetryStats` for each active run.
        The returned mapping is a snapshot; later changes to the registry
        are not reflected.

    """
    with _lock:
        return _active_runs.get(name, {}).copy()


def get_stats_by_run_id(run_id: int) -> RetryStats | None:
    """
    Return retry stats for a specific run id.

    Parameters
    ----------
    run_id : int
        Identifier returned by :func:`get_current_run_id`.

    Returns
    -------
    RetryStats | None
        Stats of the run, or ``None`` if the run has already finished.

    """
    with _lock:
        for runs in list(_active_runs.values()):
            if (stats := runs.get(run_id)) is not None:
                return stats
    return None


class RetryContext:
    """
    Context manager that registers a retry run and installs its stats as the current retry state.

    On exit, the stats are removed from the global registry and the
    previous context state is restored.

    Parameters
    ----------
    stats : RetryStats
        Retry statistics of the loop that is starting.

    """

    __slots__ = ("_stats", "_token")

    def __init__(
        self,
        stats: RetryStats,
    ) -> None:
        self._stats = stats
        self._token: contextvars.Token[RetryStats | None] | None = None

    def __enter__(self) -> Self:
        self._token = self._set_current_stats()
        self._register()
        return self

    def __exit__(
        self,
        *exc_info: object,
    ) -> None:
        self._unregister()
        self._reset_current_stats()

    def _register(self) -> None:
        stats = self._stats

        with _lock:
            _active_runs.setdefault(stats.attempt.fname, {})[id(stats)] = stats

    def _unregister(self) -> None:
        stats = self._stats

        with _lock:
            runs = _active_runs.get(stats.attempt.fname)

            if runs is None:
                return

            runs.pop(id(stats), None)

            if not runs:
                _ = _active_runs.pop(stats.attempt.fname, None)

    def _set_current_stats(self) -> contextvars.Token[RetryStats | None]:
        return _current_stats.set(self._stats)

    def _reset_current_stats(self) -> None:
        if self._token is not None:
            _current_stats.reset(self._token)
