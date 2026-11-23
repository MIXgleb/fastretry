  # Cookbook

Copy-pasteable recipes for the situations where retries are usually needed.
Every recipe shows only the options that matter for the case; the rest stay at
their defaults (see the {doc}`index` page and the {doc}`api` reference).

## HTTP requests

Transport failures (timeouts, connection resets, protocol errors) are worth a
retry; a `4xx` response is not. With `httpx` the first group raises
`httpx.TransportError`, the second one `httpx.HTTPStatusError`:

```python
import httpx

from fastretry import retry
from fastretry.delays import ExponentialDelay


@retry(
    attempts=4,
    delay=ExponentialDelay(delay=0.5, max_delay=8.0),
    jitter="full",
    retry_on=httpx.TransportError,
)
def fetch_user(user_id: int) -> bytes:
    response = httpx.get(f"https://api.example.com/users/{user_id}", timeout=5.0)
    response.raise_for_status()
    return response.content
```

`jitter="full"` spreads the retries of many clients, so they do not reconnect
in lockstep after an outage of the remote service.

With `requests` the equivalents are `requests.ConnectionError` and
`requests.Timeout`:

```python
import requests

from fastretry import retry
from fastretry.delays import ExponentialDelay


@retry(
    attempts=4,
    delay=ExponentialDelay(delay=0.5, max_delay=8.0),
    retry_on=(requests.ConnectionError, requests.Timeout),
)
def fetch_user(user_id: int) -> bytes:
    response = requests.get(f"https://api.example.com/users/{user_id}", timeout=5.0)
    response.raise_for_status()
    return response.content
```

## Async clients

For a coroutine function use the regular `retry`: it awaits the coroutine and
returns a coroutine function, so no extra plumbing is needed:

```python
import httpx

from fastretry import retry
from fastretry.delays import ExponentialDelay

client = httpx.AsyncClient(timeout=5.0)


@retry(
    attempts=4,
    delay=ExponentialDelay(delay=0.5, max_delay=8.0),
    jitter="full",
    retry_on=httpx.TransportError,
)
async def fetch_user(user_id: int) -> bytes:
    response = await client.get(f"https://api.example.com/users/{user_id}")
    response.raise_for_status()
    return response.content
```

Create the client once, outside the decorated function: a client created per
attempt leaks connections and defeats the retry.

`retry_async` is not needed here: it exists for **sync** callables that must run
in an executor (next recipe). When a code base wants one decorator that always
returns a coroutine, for sync and async callables alike, import it under the
usual name:

```python
from fastretry import retry_async as retry
```

## A blocking call inside an async application

This is the case `retry_async` exists for: it accepts a **sync** callable and
runs every attempt in an executor, so the event loop keeps serving other tasks
while the call blocks:

```python
from pathlib import Path

from fastretry import retry_async


@retry_async(attempts=3, delay=1.0)
def read_report(path: Path) -> bytes:
    return path.read_bytes()


async def handler() -> None:
    data = await read_report(Path("/var/reports/daily.csv"))
```

The running loop's default thread pool is used. Pass
`retry_async(..., executor=my_executor)` to use
[an executor of your own](https://docs.python.org/3/library/concurrent.futures.html#executor-objects),
for example a bounded one.

## Database "locked" errors

SQLite serializes writers, so `database is locked` is a transient error worth
retrying with a short exponential backoff:

```python
import sqlite3

from fastretry import retry
from fastretry.delays import ExponentialDelay


@retry(
    attempts=5,
    delay=ExponentialDelay(delay=0.05, max_delay=1.0),
    jitter="full",
    retry_on=sqlite3.OperationalError,
)
def bump_counter(connection: sqlite3.Connection, key: str) -> None:
    connection.execute("UPDATE counters SET value = value + 1 WHERE key = ?", (key,))
    connection.commit()
```

`OperationalError` also covers unrecoverable problems (a missing table, a
read-only database), because retrying is decided by exception type. When the
distinction matters, wrap the call and raise a dedicated type:

```python
class DatabaseBusy(Exception):
    """The database is locked by another writer."""


@retry(attempts=5, delay=0.05, retry_on=DatabaseBusy)
def bump_counter(connection: sqlite3.Connection, key: str) -> None:
    try:
        connection.execute("UPDATE counters SET value = value + 1 WHERE key = ?", (key,))
        connection.commit()
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc):
            raise
        raise DatabaseBusy from exc
```

## A fallback instead of an exception

When a missing value is acceptable, `return_default_value` turns the failure
into a value. No exception group is raised, and type checkers see the widened
return type:

```python
from fastretry import retry


@retry(attempts=3, delay=0.5, return_default_value=None)
def fetch_feature_flag(name: str) -> dict[str, bool] | None:
    return remote_flags()[name]


flag = fetch_feature_flag("new-checkout")  # dict[str, bool] | None
if flag is None:
    flag = {"enabled": False}
```

Prefer an explicit "degraded mode" value over a bare `None` when the caller
would have to guess what `None` means.

## A deadline for the whole call

`max_time` is the counterpart of `attempts` for a caller that has a deadline
rather than a retry count: a web request, a CLI invocation, a health check.
The budget covers the attempts *and* the delays, and a retry that could not
start inside it is not scheduled at all:

```python
from fastretry import retry
from fastretry.delays import ExponentialDelay


@retry(
    attempts=10,
    delay=ExponentialDelay(delay=0.5, max_delay=8.0),
    jitter="full",
    max_time=15.0,
)
def fetch_export(export_id: str) -> bytes:
    return client.exports.get(export_id).read()
```

The function is always called at least once, and an attempt that already
started is allowed to finish, so `max_time` bounds the waiting, not the
duration of a single call. When the budget runs out the failure is reported
like an exhausted retry: the exception group names the budget and
`stats.deadline_reached` is `True` for callbacks and introspection.

Use it together with `attempts` when both limits matter: whichever comes first
stops the loop.

## Custom delay

`delay` also accepts a callable, so a schedule that is neither fixed nor
exponential needs no extra library. The callable receives the 1-based index of
the failed attempt that is about to be retried and the delay used after the
previous attempt (`None` on the first retry), and returns the base delay:

```python
from fastretry import retry


def batch_wait(retry_index: int, previous_delay: float | None) -> float:
    """Retry a batch job after 10 s, then 30 s, then 60 s, then every 120 s."""
    schedule = (10.0, 30.0, 60.0)
    return schedule[retry_index - 1] if retry_index <= len(schedule) else 120.0


@retry(attempts=6, delay=batch_wait)
def upload(batch: list[str]) -> None: ...
```

Notes:

- the returned value is the base delay; `jitter` is applied on top of it
  (`jitter_for_fixed` is the default when `jitter` is omitted);
- the value must be finite and non-negative — anything else raises
  `ValueError` instead of silently sleeping or hanging;
- `previous_delay` already includes jitter, so a callable can adapt to the
  delays that were actually slept.

The `WaitCallable` and `Delay` aliases from `fastretry.delays` describe the
signature, if you want to annotate the callable.

## Metrics and structured logs

Callbacks receive a `RetryStats` object with everything known about the
current call: the attempt index, timings, the last exception and the
collected exceptions. `RetryStats.log_extra` is a ready-to-use mapping for the
`extra` argument of `logging`:

```python
import logging

from fastretry import retry
from fastretry.callbacks import RetryStats

logger = logging.getLogger(__name__)


def on_retry(stats: RetryStats) -> None:
    logger.warning(
        "attempt %d failed: %r",
        stats.attempt.retry_index,
        stats.attempt.last_exception,
        extra=dict(stats.log_extra),
    )


def on_failure(stats: RetryStats) -> None:
    metrics.increment(
        "retry.exhausted",
        tags={
            "function": stats.attempt.fname,
            "attempts": str(stats.attempt.retry_index),
            "last_error": type(stats.attempt.last_exception).__name__,
        },
    )


@retry(attempts=3, callbacks={"on_retry": on_retry, "on_failure": on_failure})
def sync_order(order_id: int) -> None: ...
```

Notes:

- passing `on_retry` **replaces** the built-in callback, so the default log
  line for retries disappears — log it yourself (as above) or call
  `fastretry.callbacks.default_on_retry(stats)` first to keep it;
- `on_retry` runs after **every** failed attempt, including the last one, where
  no further attempt follows; `on_failure` runs once after it. Do not count
  `on_retry` calls as "retries that will still happen";
- `stats.attempt.attempt_duration` and `stats.attempt.total_elapsed` exclude
  callbacks and delays, while `stats.attempt.attempt_durations` keeps the
  duration of every finished attempt;
- callbacks must be fast: a blocking callback delays the retry loop.

## Per-request overrides

`config.context` installs a fresh copy of the defaults for the duration of the
block, isolated to the current asyncio task or thread. This is the place for
"this endpoint needs more attempts" without touching the global defaults:

```python
from fastretry import config, retry
from fastretry.delays import ExponentialDelay


async def handle_webhook(payload: dict[str, str]) -> bytes:
    with config.context(
        attempts=6,
        delay=ExponentialDelay(delay=0.2, max_delay=5.0),
        jitter_for_exponential="full",
    ):

        @retry
        def call_partner_api() -> bytes:
            return partner_client.send(payload)

        return call_partner_api()
```

A decorator reads the defaults when it is created, so create the decorated
function inside the `with` block (as above) or pass the options to
`@retry(...)` directly.

## Configuration mistakes

Keyword arguments are validated as soon as the decorator is created, and values
are validated when it is applied to a function, so a typo never hides until the
retry loop is already running:

```python
from fastretry import retry

retry(attempt=4)
# TypeError: retry() got an unexpected keyword argument 'attempt';
# did you mean `attempts`?

retry(unwrap_single_exception=True)
# TypeError: `unwrap_single_exception` is a global option,
# configure it via `config.retry(...)`


@retry(attempts="3")
def fetch() -> bytes: ...


# TypeError: attempts must be an int, got str
```

Global defaults follow the same rules: `config.retry(attempts="3")` is accepted,
and the error is raised when the next decorator is created. That makes a
misconfigured decorator fail in the test that imports the module, not in
production after the third timeout.

## Inspecting retries at runtime

Introspection answers three questions without threading state through the call
chain: whether a retry is running, what it has already tried, and which runs are
active elsewhere in the process.

```python
import logging

from fastretry import retry
from fastretry.callbacks import RetryStats
from fastretry.introspection import get_current_stats, is_retrying

logger = logging.getLogger(__name__)


def on_retry(stats: RetryStats) -> None:
    if is_retrying():
        logger.warning(
            "attempt %d of %d failed",
            stats.attempt.retry_index,
            stats.decorator.attempts,
        )


@retry(attempts=3, callbacks={"on_retry": on_retry})
def fetch(url: str) -> bytes:
    stats = get_current_stats()
    assert stats is not None  # the call is inside a retry loop
    ...
```

`is_retrying()` without arguments reports the current context: it is true
inside the wrapped callable, in its callbacks and during delays.
`get_current_stats()` returns the same live object callbacks receive, so
`attempt.retry_index`, `attempt.attempt_duration` and `attempt.last_exception`
reflect the attempt in progress. Treat it as read-only.

`get_current_run_id()` returns an id that is unique in the process and is never
reused. Combined with `get_stats_by_run_id()`, another thread or task can look
at a run it did not start:

```python
from fastretry.introspection import get_current_run_id, get_stats_by_run_id

run_id = get_current_run_id()  # captured inside the retried callable
stats = get_stats_by_run_id(run_id)  # from a watchdog, health check, etc.
```

To inspect runs by function instead of by id, pass the decorated callable, its
qualified name, an `asyncio.Task` or a `functools.partial`: `is_retrying(fetch)`
and `get_stats_for(fetch)` report the runs of that callable that are active
right now. Several threads may run the same function concurrently, so
`get_stats_for` maps run id to `RetryStats`. The mapping is a snapshot, but the
values are live objects that keep updating. Call `RetryStats.snapshot()` when
you need a detached copy that no longer changes, for example to report several
fields that belong to the same moment. `get_active_runs()` does the same for
every function in the process, which is what a diagnostics endpoint usually
wants:

```python
from fastretry.introspection import get_active_runs

for run_id, stats in get_active_runs().items():
    logger.info("%s: attempt %d", stats.attempt.fname, stats.attempt.retry_index)
```

The registry is cleaned up when the call finishes, including on failure, and
the context view is per task and per thread, so concurrent `asyncio` tasks do
not see each other's stats.

## Tests

Two knobs keep tests fast and quiet: `config.reset()` after each test and
`disable_logging=True` on the decorator under test.

```python
import pytest

from fastretry import config, retry


@pytest.fixture(autouse=True)
def _reset_fastretry() -> None:
    config.reset()


def test_fetch_retries_once() -> None:
    calls = []

    @retry(attempts=2, delay=0, disable_logging=True)
    def fetch() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError
        return "ok"

    assert fetch() == "ok"
    assert len(calls) == 2
```

`config.context(...)` is the lighter alternative when only one test needs
different defaults: it restores the previous state when the block exits, even
if the test fails.
