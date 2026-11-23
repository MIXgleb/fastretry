"""
Shared background event loop for async callbacks.

A single daemon thread runs one event loop for the whole process, and async
callbacks of synchronous retried functions are submitted to that loop
instead of starting a new thread (and a new event loop) per invocation.

The implementation deliberately trades isolation for speed, so it guards
against the known failure modes of a process-wide loop:

- a :exc:`BaseException` raised by a callback does not kill the loop thread:
  it is captured and re-raised in the calling thread;
- a loop that died for any other reason is detected while waiting, and the
  caller gets :exc:`RuntimeError` instead of blocking forever;
- after a ``fork()`` the child process starts its own loop;
- the loop is stopped and finalized on interpreter exit, so async
  generators, default executors, and pending callbacks are not leaked;
- re-entrant calls are detectable with :meth:`SharedLoop.is_owner_thread`,
  so callers fall back to a per-call thread instead of deadlocking.

Note that callbacks are serialized: one slow or blocking callback delays
every other callback that uses the shared loop in this process.
"""

import asyncio
import atexit
import concurrent.futures
import contextlib
import os
import threading
from typing import (
    Final,
    Literal,
)

from fastretry._compat.aliases import (
    Coro,
)

type AsyncCallbackMode = Literal[
    "thread_per_call",
    "shared_loop_when_running",
    "shared_loop_always",
]
"""
How async callbacks of synchronous functions are dispatched.

- ``"thread_per_call"`` — a new thread with its own event loop for every
  invocation when an event loop is already running, otherwise
  :func:`asyncio.run`. The safest and most isolated mode.
- ``"shared_loop_when_running"`` — a process-wide shared loop when an event
  loop is already running; :func:`asyncio.run` otherwise.
- ``"shared_loop_always"`` — the shared loop in every case.

Every mode that uses the shared loop has the same trade-offs: callbacks are
serialized in one thread, they run in a dedicated daemon thread rather than
the calling one, and the loop lifecycle is shared by the whole process.
"""

ASYNC_CALLBACK_MODES: Final[frozenset[str]] = frozenset(
    {
        "thread_per_call",
        "shared_loop_when_running",
        "shared_loop_always",
    },
)
"""Every supported :data:`AsyncCallbackMode` value."""

_WAIT_SLICE: Final[float] = 0.25
"""Seconds a caller waits for a callback before re-checking the loop health."""

_START_TIMEOUT: Final[float] = 5.0
"""Seconds :meth:`SharedLoop._start` waits for the new loop to start running."""

_SHUTDOWN_TIMEOUT: Final[float] = 5.0
"""Seconds :meth:`SharedLoop.shutdown` waits for the loop thread to exit."""


class SharedLoop:
    """
    Lazy singleton event loop running in a dedicated daemon thread.

    Use :meth:`run_callback` to execute a callback coroutine and wait for its
    completion, and :meth:`is_owner_thread` to detect re-entrant calls made
    from the loop itself.

    """

    __slots__ = (
        "_lock",
        "_loop",
        "_pid",
        "_thread",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pid = 0

    def is_owner_thread(self) -> bool:
        """
        Check whether the current thread runs the shared loop.

        Returns
        -------
        bool
            ``True`` when called from the shared loop thread. Callers must
            not use :meth:`run_callback` in that case: waiting for the loop
            from inside the loop can never finish.

        """
        thread = self._thread
        return thread is not None and threading.current_thread() is thread

    def run_callback(
        self,
        coro: Coro[None],
    ) -> None:
        """
        Run a callback coroutine on the shared loop and wait for it.

        Parameters
        ----------
        coro : Coro[None]
            Callback coroutine to execute.

        Notes
        -----
        An exception raised by the callback is re-raised in the calling
        thread. If the loop stops before the callback completes, a
        :exc:`RuntimeError` is raised instead of blocking forever.

        """
        loop = self._ensure_loop()
        errors: list[BaseException] = []
        future = asyncio.run_coroutine_threadsafe(
            coro=self._run_guarded(coro, errors),
            loop=loop,
        )

        self._wait(future, loop=loop, coro=coro)

        if errors:
            raise errors[0]

    def shutdown(self) -> None:
        """Stop the loop thread and finalize the loop, if it was started."""
        loop = self._loop
        thread = self._thread
        self._loop = None
        self._thread = None
        self._pid = 0

        if loop is None or thread is None:
            return

        if loop.is_running():
            _ = loop.call_soon_threadsafe(loop.stop)

        thread.join(timeout=_SHUTDOWN_TIMEOUT)

    def _wait(
        self,
        future: concurrent.futures.Future[None],
        *,
        loop: asyncio.AbstractEventLoop,
        coro: Coro[None],
    ) -> None:
        """
        Wait for a callback, detecting a dead loop instead of hanging.

        Parameters
        ----------
        future : concurrent.futures.Future[None]
            Chained future of the callback task.
        loop : asyncio.AbstractEventLoop
            Loop the callback was submitted to.
        coro : Coro[None]
            Callback coroutine, closed if the loop is gone.

        Raises
        ------
        RuntimeError
            If the loop stopped or died before the callback completed.

        """
        while True:
            try:
                _ = future.result(timeout=_WAIT_SLICE)
            except concurrent.futures.TimeoutError:
                if self._is_healthy(loop):
                    continue

                self._abandon(coro)
                msg = (
                    "The shared callback event loop stopped before the callback "
                    "completed, so its result was lost. Use "
                    "config.retry(async_callback_mode='thread_per_call') or a "
                    "per-call loop for callbacks that must not share a loop."
                )
                raise RuntimeError(msg) from None
            return

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """
        Return a healthy shared loop, creating it when needed.

        Returns
        -------
        asyncio.AbstractEventLoop
            Running loop owned by the dedicated thread.

        """
        loop = self._loop

        if loop is not None and self._is_healthy(loop):
            return loop

        if self._pid != 0 and self._pid != os.getpid():
            # A fork happened: only the current thread survived, so there is
            # no second thread to race with and the inherited lock must not
            # be reused (it may have been held by a thread that is now gone).
            return self._start()

        with self._lock:
            loop = self._loop

            if loop is not None and self._is_healthy(loop):
                return loop

            return self._start()

    def _start(self) -> asyncio.AbstractEventLoop:
        """
        Start a new loop thread.

        Returns
        -------
        asyncio.AbstractEventLoop
            Newly started loop.

        """
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        thread = threading.Thread(
            target=self._loop_thread_main,
            args=(loop, ready),
            name="fastretry-callback-loop",
            daemon=True,
        )
        thread.start()
        _ = ready.wait(timeout=_START_TIMEOUT)

        self._loop = loop
        self._thread = thread
        self._pid = os.getpid()

        return loop

    def _is_healthy(
        self,
        loop: asyncio.AbstractEventLoop,
    ) -> bool:
        """
        Check whether a loop is owned by this process and still running.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            Loop to check.

        Returns
        -------
        bool
            ``True`` when the loop can accept new callbacks.

        """
        thread = self._thread

        return (
            self._pid == os.getpid()
            and thread is not None
            and thread.is_alive()
            and not loop.is_closed()
            and loop.is_running()
        )

    @staticmethod
    def _abandon(coro: Coro[None]) -> None:
        """
        Close a callback whose loop is gone.

        The chained future is intentionally left alone: cancelling it would
        schedule a cancellation on the already closed loop and log a spurious
        ``RuntimeError: Event loop is closed`` traceback.

        Parameters
        ----------
        coro : Coro[None]
            Callback coroutine, closed to avoid "never awaited" warnings.

        """
        with contextlib.suppress(RuntimeError):
            coro.close()

    @staticmethod
    def _loop_thread_main(
        loop: asyncio.AbstractEventLoop,
        ready: threading.Event,
    ) -> None:
        """
        Run a loop until it is stopped, then finalize and close it.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            Loop owned by the current thread.
        ready : threading.Event
            Set once the loop is actually running, so that the thread that
            started it can return a ready-to-use loop.

        """
        asyncio.set_event_loop(loop)
        _ = loop.call_soon(ready.set)

        try:
            loop.run_forever()
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()

    @staticmethod
    async def _run_guarded(
        coro: Coro[None],
        errors: list[BaseException],
    ) -> None:
        """
        Await a callback coroutine, capturing any :exc:`BaseException`.

        Capturing is what keeps the shared loop thread alive: a ``BaseException``
        escaping a task would propagate out of ``run_forever`` and kill the
        thread, turning every later callback into a silent hang.

        Parameters
        ----------
        coro : Coro[None]
            Callback coroutine.
        errors : list[BaseException]
            Collector for the captured exception; it is re-raised by the caller.

        """
        try:
            await coro
        except BaseException as exc:  # ruff: ignore[blind-except]
            errors.append(exc)


shared_loop: Final[SharedLoop] = SharedLoop()
"""Process-wide shared loop used when ``async_callback_mode`` asks for it."""

_ = atexit.register(shared_loop.shutdown)
"""Stop the loop thread on interpreter exit, so it is not left running."""
