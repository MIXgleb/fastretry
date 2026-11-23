"""
Runtime introspection of retry runs in progress.

Two views are exposed:

- the state of the retry run active in the current context, through
  :func:`get_current_stats` and :func:`get_current_run_id`;
- a process-wide registry of the runs executing right now, through
  :func:`is_retrying`, :func:`get_stats_for`, :func:`get_stats_by_run_id`
  and :func:`get_active_runs`.

The context view is per task and per thread and costs a single
:mod:`contextvars` lookup; it returns the live instance the retry loop
updates. The registry is shared by the whole process and guarded by a
lock: every call registers and unregisters itself, and runs may start and
finish in different threads at the same time. Registry lookups return the
live instances as well; call :meth:`RetryStats.snapshot` when a detached
copy is needed.
"""

import contextvars
import dataclasses as dc
import functools
import itertools
import threading
from collections.abc import (
    Callable,
    Iterator,
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


@dc.dataclass(slots=True, frozen=True)
class _CurrentRun:
    """
    Retry run installed in the current context.

    Attributes
    ----------
    stats : RetryStats
        Statistics of the run in progress.
    run_id : int
        Registry id of the run, unique within the process.

    """

    stats: RetryStats
    run_id: int


_lock: Final[threading.Lock] = threading.Lock()
"""Guards the process-wide registry of active runs."""

_run_ids: Final[Iterator[int]] = itertools.count(1)
"""Source of run ids; an id is never reused within a process."""

_current_run: Final[contextvars.ContextVar[_CurrentRun | None]] = contextvars.ContextVar(
    "retry_current_run",
    default=None,
)
"""Retry run active in the current context, if any."""

_active_runs: Final[dict[int, RetryStats]] = {}
"""Statistics of every retry run in progress, keyed by run id."""


def _qualname_of(target: object) -> str | None:
    """
    Return the qualified name of a callable, task or partial.

    Tasks and partials do not expose ``__qualname__`` themselves, so they
    are unwrapped: a task contributes the qualified name of its coroutine,
    and a partial the one of its wrapped callable.

    Parameters
    ----------
    target : object
        Callable, coroutine, :class:`asyncio.Task` or
        :class:`functools.partial`.

    Returns
    -------
    str | None
        Qualified name, or ``None`` if the target cannot be resolved.

    """
    while isinstance(target, functools.partial):
        target = target.func

    get_coro = getattr(target, "get_coro", None)
    if callable(get_coro):
        target = get_coro()

    name = getattr(target, "__qualname__", None)
    return name if isinstance(name, str) else None


def _resolve_fname(target: str | Callable[..., object]) -> str:
    """
    Return the registry key for a qualified name or a decorated callable.

    Callables are resolved through their ``__qualname__``; an
    :class:`asyncio.Task` through the qualified name of its coroutine, and
    a :class:`functools.partial` through the wrapped callable, so a run
    can be found by any of them.

    Parameters
    ----------
    target : str | Callable
        Qualified name, or a callable decorated with
        :func:`~fastretry.retry` or :func:`~fastretry.retry_async`.

    Returns
    -------
    str
        Qualified name of the callable, or the string itself.

    """
    if isinstance(target, str):
        return target

    name = _qualname_of(target)
    return name if name is not None else "<anonymous>"


def is_retrying(target: str | Callable[..., object] | UnsetType = UNSET) -> bool:
    """
    Check whether a retry loop is active.

    Without an argument, checks the current context: ``True`` inside the
    wrapped callable, in its callbacks and during its delays. With a
    callable, an :class:`asyncio.Task`, a ``functools.partial`` or a
    qualified name, checks whether any run of it is active anywhere in the
    process, including other threads and tasks.

    Parameters
    ----------
    target : str | Callable | UnsetType, ``optional``
        Callable, task, partial or qualified name to check process-wide,
        by default ``UNSET`` to check the current context instead.

    Returns
    -------
    bool
        ``True`` if a matching retry loop is active.

    """
    if isinstance(target, UnsetType):
        return get_current_stats() is not None

    fname = _resolve_fname(target)

    with _lock:
        return any(stats.attempt.fname == fname for stats in _active_runs.values())


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
    run = _current_run.get()
    return None if run is None else run.stats


def get_current_run_id() -> int | None:
    """
    Return the run id of the retry loop active in the current context.

    The run id is a process-wide identifier assigned to the call when it
    starts. Unlike :func:`id`, it is never reused, so a value obtained in
    one thread or task can be passed to :func:`get_stats_by_run_id` from
    another one and will never resolve to a later run.

    Returns
    -------
    int | None
        Run id, or ``None`` if no retry loop is active.

    """
    run = _current_run.get()
    return None if run is None else run.run_id


def get_stats_for(target: str | Callable[..., object]) -> Mapping[int, RetryStats]:
    """
    Return active retry runs of a callable.

    A function may be executed concurrently in several threads or tasks.
    Each execution has its own :class:`RetryStats` instance and its own
    run id, so the result maps run ids to stats. An empty mapping is
    returned if no run of the function is active.

    The values are live instances owned by their retry loops: treat them
    as read-only and call :meth:`RetryStats.snapshot` when the data is
    passed to another thread, task or storage that outlives the run.

    Parameters
    ----------
    target : str | Callable
        Callable, qualified name, :class:`asyncio.Task` or
        ``functools.partial``; a callable contributes its
        ``__qualname__``, which is what ``AttemptState.fname`` reports.

    Returns
    -------
    Mapping[int, RetryStats]
        Mapping of run id to the live :class:`RetryStats` of each active
        run. The mapping is a snapshot: later registrations are not
        reflected in it, but the values keep updating as the runs
        progress. Call :meth:`RetryStats.snapshot` for a detached copy.

    """
    fname = _resolve_fname(target)

    with _lock:
        return {
            run_id: stats for run_id, stats in _active_runs.items() if stats.attempt.fname == fname
        }


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
        Live stats of the run, or ``None`` if the run has already
        finished. The value keeps updating and is read-only; call
        :meth:`RetryStats.snapshot` for a detached copy.

    """
    with _lock:
        return _active_runs.get(run_id)


def get_active_runs() -> Mapping[int, RetryStats]:
    """
    Return every retry run active in the process.

    Useful for diagnostics: a health check or a debug endpoint can report
    what is being retried right now without knowing function names. The
    values are live instances owned by their retry loops: treat them as
    read-only and call :meth:`RetryStats.snapshot` when the data leaves
    the process or outlives the run.

    Returns
    -------
    Mapping[int, RetryStats]
        Mapping of run id to the live :class:`RetryStats` of each active
        run. The mapping is a snapshot: later registrations are not
        reflected in it, but the values keep updating. Call
        :meth:`RetryStats.snapshot` for detached copies.

    """
    with _lock:
        return dict(_active_runs)


class RetryContext:
    """
    Register a retry run and install its stats as the current retry state.

    Entered by the retry wrappers before the first attempt and exited
    after the last one, so the run is visible to introspection for the
    whole call. Registration is process-wide; the current-state part is
    scoped to the task or thread that entered the context.

    Parameters
    ----------
    stats : RetryStats
        Retry statistics of the loop that is starting.

    """

    __slots__ = (
        "_previous",
        "_run_id",
        "_stats",
    )

    def __init__(
        self,
        stats: RetryStats,
    ) -> None:
        self._stats = stats
        self._previous: _CurrentRun | None = None
        self._run_id = 0  # replaced by __enter__, 0 is never handed out

    def __enter__(self) -> Self:
        with _lock:
            self._run_id = next(_run_ids)
            _active_runs[self._run_id] = self._stats

        self._previous = _current_run.get()
        _ = _current_run.set(_CurrentRun(stats=self._stats, run_id=self._run_id))
        return self

    def __exit__(
        self,
        *exc_info: object,
    ) -> None:
        _ = _current_run.set(self._previous)

        with _lock:
            _ = _active_runs.pop(self._run_id, None)
