# Migration guide

`fastretry` covers the common part of `tenacity`, `backoff` and `retry`: a
number of attempts, a delay between them, and a decision which exceptions are
worth retrying. This page maps the options of those libraries to `fastretry`
and lists the behavioral differences that bite during a migration.

## From tenacity

```python
# tenacity
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=0.5, max=8),
    retry=retry_if_exception_type(IOError),
    reraise=True,
)
def fetch() -> bytes: ...
```

```python
# fastretry
from fastretry import ExponentialDelay, retry


@retry(
    attempts=4,
    delay=ExponentialDelay(delay=0.5, max_delay=8.0),
    retry_on=IOError,
)
def fetch() -> bytes: ...
```

| tenacity | fastretry |
|---|---|
| `stop_after_attempt(n)` | `attempts=n` |
| `wait_fixed(s)` | `delay=s` |
| `wait_exponential(multiplier=m, max=x)` | `delay=ExponentialDelay(delay=m, max_delay=x)` |
| `wait_random(min, max)` | `delay=...` + `jitter="full"` |
| `wait_exponential_jitter(...)` | `delay=ExponentialDelay(...)` + `jitter="equal"` |
| `retry_if_exception_type(E)` | `retry_on=E` |
| `retry_if_not_exception_type(E)` | `no_retry_on=E` |
| `retry=retry_if_result(...)` | not supported yet |
| `reraise=True` | `config.retry(unwrap_single_exception=True)` for a single failure, see below |
| `before_sleep=...` | `callbacks={"on_retry": ...}` |
| `after=...` | `callbacks={"on_success": ..., "on_retry": ..., "on_failure": ...}` |
| `stop_after_delay(...)` | not supported yet |
| `Retrying(...)` object | global defaults via `config.retry(...)`, or `@retry(...)` |

`jitter` is a strategy name, not a number: `"none"` (default), `"full"`
(`random(0, delay)`), `"equal"` (half of the delay is fixed, half is random)
and `"decorrelated"`.

There is no need for a separate decorator for coroutine functions: `retry`
handles both kinds of callables and awaits coroutine functions directly.
`retry_async` is only for **sync** callables that must run in an executor; it
always returns a coroutine function, so callers `await` it.

## From backoff

```python
# backoff
import backoff


@backoff.on_exception(backoff.expo, IOError, max_tries=4, max_value=8)
def fetch() -> bytes: ...
```

```python
# fastretry
from fastretry import ExponentialDelay, retry


@retry(attempts=4, delay=ExponentialDelay(delay=1.0, max_delay=8.0), retry_on=IOError)
def fetch() -> bytes: ...
```

| backoff | fastretry |
|---|---|
| `max_tries=n` | `attempts=n` |
| `backoff.constant` | `delay=<float>` |
| `backoff.expo` / `backoff.fibo` | `delay=ExponentialDelay(...)` (exponential only) |
| `max_value=x` | `delay=ExponentialDelay(delay=s, max_delay=x)` |
| `jitter=backoff.full_jitter` | `jitter="full"` |
| `backoff.on_predicate(...)` | not supported yet |
| `on_backoff=...` | `callbacks={"on_retry": ...}` |
| `on_giveup=...` | `callbacks={"on_failure": ...}` |
| `giveup=...` | not supported yet |
| `max_time=...` | not supported yet |

## From `retry`

```python
# retry
from retry import retry


@retry(tries=4, delay=0.5, backoff=2, exceptions=IOError)
def fetch() -> bytes: ...
```

```python
# fastretry
from fastretry import ExponentialDelay, retry


@retry(
    attempts=4,
    delay=ExponentialDelay(delay=0.5, backoff_factor=2, max_delay=8.0),
    retry_on=IOError,
)
def fetch() -> bytes: ...
```

| retry | fastretry |
|---|---|
| `tries=n` | `attempts=n` |
| `delay=s` | `delay=s` |
| `backoff=f` | `delay=ExponentialDelay(delay=s, backoff_factor=f)` |
| `max_delay=x` | `delay=ExponentialDelay(delay=s, max_delay=x)` |
| `jitter=(min, max)` | no direct equivalent; `jitter="full"` or `"equal"` jitter the computed delay proportionally |
| `exceptions=E` | `retry_on=E` |
| `logger=...` | `config.logging(...)` |

## Behavioral differences

### The failure is an exception group

This is the difference that shows up first. `tenacity` (with `reraise=True`)
and `backoff` re-raise the **last** exception, so `except ValueError` keeps
working. `fastretry` collects every attempt and raises an `ExceptionGroup`, so
the caller sees all failures at once:

```python
from fastretry import retry


@retry(attempts=3, delay=0)
def fetch() -> bytes:
    raise ValueError("boom")


try:
    fetch()
except* ValueError as group:
    for exc in group.exceptions:
        ...
```

For a drop-in migration, enable unwrapping once at application startup — a
failure with exactly one collected exception is then re-raised as is:

```python
from fastretry import config

config.retry(unwrap_single_exception=True)
```

With `attempts=1` (the default) that restores the familiar `except ValueError`
behavior exactly; with more attempts, two or more failures still produce a
group, because there is no single exception to re-raise.

### One attempt by default

`@retry` without arguments performs **one** attempt: `attempts` defaults to 1
and is meant to be configured globally. `tenacity` without a `stop` retries
forever, and `backoff` without `max_tries` does the same, so a migrated
decorator that relied on the library default must set the number of attempts
explicitly:

```python
from fastretry import config

config.retry(attempts=3, delay=1.0)
```

### Only attempts and delay

There is no deadline, no total time budget, no result predicate and no custom
wait callable yet; retries stop when `attempts` is exhausted. These features are
planned, but not implemented: the current release has no equivalent of `stop`,
`wait`, `retry_if_result` or `before_sleep` from `tenacity`.

### Callbacks instead of hooks

Callbacks are a fixed set of three hooks, `on_success`, `on_retry` and
`on_failure`, and each one replaces the corresponding built-in behavior (which
is logging). JSON logs get the same fields through `RetryStats.log_extra`, so
`before_sleep_log`/`after_log` equivalents are a few lines, see the
{doc}`cookbook` page.

### Configuration is global or per decorator

Options are read when a decorator is created, either from the arguments of
`@retry(...)` or from the global defaults set by `config.retry(...)`,
`config.logging(...)` and `config.context(...)`. There is no long-lived
`Retrying` object with per-call statistics. Use `config.context(...)` for a
temporary override of the defaults, for example per asyncio task.
