# fastretry

[![test](https://github.com/MIXgleb/fastretry/actions/workflows/ci.yml/badge.svg)](https://github.com/MIXgleb/fastretry/actions/workflows/ci.yml)
![](https://img.shields.io/badge/Coverage-100%25-83A603.svg?prefix=$coverage$)
[![Python](https://img.shields.io/pypi/pyversions/fastretry)](https://pypi.org/project/fastretry/)
[![PyPI](https://img.shields.io/pypi/v/fastretry)](https://pypi.org/project/fastretry/)


Retry decorator for synchronous and asynchronous functions.

- Sync and async functions, selected automatically.
- Fixed or exponential backoff, with optional jitter.
- Lifecycle callbacks for success, retry, and failure.
- Configurable per decorator or globally.
- Run sync functions in an executor from async code.
- Runtime introspection of the retry in progress (`fastretry.introspection`):
  `is_retrying()`, `get_current_stats()` and lookups of other runs
  (`get_stats_for()`, `get_active_runs()`).
- 100% test coverage.

**Documentation:** <https://fastretry.readthedocs.io/>

## Installation

```bash
pip install fastretry
```

Requires Python 3.13 or newer.

## Usage

### Sync function

```python
from fastretry import retry


@retry(attempts=3, delay=1.0)
def fetch() -> bytes: ...
```

### Async function

Use the regular `retry` for coroutine functions: it awaits them directly
and returns a coroutine function.

```python
from fastretry import retry


@retry(attempts=3, delay=1.0)
async def fetch() -> bytes: ...
```

### Sync function, called asynchronously

Use `retry_async` to run a sync function in an executor so the event
loop is not blocked. The decorator always returns a coroutine function,
so callers must `await` it.

```python
from fastretry import retry_async


@retry_async(attempts=3, delay=1.0)
def blocking_io() -> bytes: ...


async def main() -> None:
    data = await blocking_io()
```

`retry_async` is meant for sync callables like this one. When a code base
wants one decorator that always returns a coroutine — for sync and async
callables alike — import it under the usual name:

```python
from fastretry import retry_async as retry
```

## Options

All options are optional and fall back to global defaults.

| Option | Description |
|---|---|
| `attempts` | Number of attempts. Default: `1`. |
| `delay` | Delay between attempts. `float` for a fixed delay, `ExponentialDelay` for exponential backoff. Default: `0`. |
| `jitter` | Jitter strategy: `"none"`, `"full"`, `"equal"`, `"decorrelated"`. |
| `return_default_value` | Value returned on failure instead of raising. |
| `retry_on` | Exception types that trigger a retry. Default: `Exception`. |
| `no_retry_on` | Exception types that are never retried. Takes precedence. |
| `callbacks` | Lifecycle callbacks: `on_success`, `on_retry`, `on_failure`. |
| `disable_logging` | Disable all logging. |
| `disable_warnings` | Disable all warnings. |
| `executor` | (`retry_async` only) Executor used to run sync functions. |

### Exponential backoff

```python
from fastretry import retry
from fastretry.delays import ExponentialDelay


@retry(attempts=5, delay=ExponentialDelay(delay=1.0, backoff_factor=2.0, max_delay=30.0))
def fetch() -> bytes: ...
```

### Jitter

```python
@retry(attempts=5, delay=ExponentialDelay(delay=1.0), jitter="full")
def fetch() -> bytes: ...
```

Strategies: `"none"`, `"full"`, `"equal"`, `"decorrelated"`.

### Return a default value instead of raising

```python
@retry(attempts=3, return_default_value=None)
def fetch() -> bytes: ...
```

When all attempts fail, the wrapper returns `return_default_value`
instead of raising. The return type is widened statically with the type of
the default value, so type checkers see `fetch` above as
`Callable[[], bytes | None]` — no changes are needed on your side.

### Retry on specific exceptions

```python
@retry(attempts=3, retry_on=(TimeoutError, ConnectionError))
def fetch() -> bytes: ...
```

### Never retry specific exceptions

```python
@retry(attempts=3, no_retry_on=ValueError)
def fetch() -> bytes: ...
```

### Callbacks

```python
from fastretry import retry
from fastretry.callbacks import RetryStats


def on_retry(stats: RetryStats) -> None:
    print(f"attempt {stats.attempt.retry_index} failed: {stats.attempt.last_exception!r}")


@retry(attempts=3, callbacks={"on_retry": on_retry})
def fetch() -> bytes: ...
```

Available keys: `on_success`, `on_retry`, `on_failure`. Callbacks may be
sync or async. Pass `None` for a key to disable that callback, or pass
`callbacks=None` to disable all of them.

#### Async callbacks on sync functions

Async callbacks are awaited in the same loop when the wrapped function is a
coroutine, so they are cheap. On a **sync** function the callback has to be
run in a loop of its own:

- when no event loop is running in the calling thread, `asyncio.run()` is
  used — cheap;
- when an event loop **is** already running, a new thread with a fresh event
  loop is used for every callback, and the caller blocks until it completes.
  This is the safest and most isolated behavior, but it costs roughly **3 ms
  per callback** (the callback still sees the caller's `contextvars`).

If callbacks are a hot path for sync functions, the dispatch can be switched
to a process-wide shared loop:

```python
from fastretry import config

config.retry(async_callback_mode="shared_loop_when_running")
```

| `async_callback_mode` | Behavior |
|---|---|
| `"thread_per_call"` (default) | `asyncio.run()` without a running loop; a new thread with its own loop per callback otherwise |
| `"shared_loop_when_running"` | a process-wide loop instead of the per-call thread (≈0.1 ms per callback); `asyncio.run()` when no loop is running |
| `"shared_loop_always"` | the process-wide loop in every case |

The shared modes trade isolation for speed: callbacks are serialized in one
daemon thread, one slow callback delays the others, and the loop is created
lazily and recreated in a `fork()`ed child. Configure them only if you
understand these trade-offs; sync callbacks are the simplest way to avoid
the cost entirely.

## Configuration

Global defaults apply to all subsequently created decorators.

```python
from fastretry import config
from fastretry.logging import LogLevel

config.retry(attempts=3, delay=1.0)
config.logging(level_success=LogLevel.INFO)
```

Per-decorator options passed to `@retry(...)` take precedence over
global defaults.

### Per-context overrides

`config.context` installs a fresh copy of the defaults for the duration
of the block. Changes are isolated to the current context: each asyncio
task or thread sees its own instance.

```python
from fastretry import config

with config.context(attempts=5, delay=2.0):
    ...
```

### Reset

```python
config.reset()
```

Restores all defaults to their factory values. Useful in tests.

## Logging

Logging is handled by the standard `logging` module through a logger
named `"fastretry"`.

A console handler writing to `sys.stderr` is installed automatically on
the first log message, so retry warnings and failures are visible
without any setup:

```python
from fastretry import retry


@retry(attempts=3)
def fetch() -> bytes: ...
```

To take full control, configure `logging` in your application
(`logging.basicConfig()`, `logging.dictConfig()`, or a handler on the
`"fastretry"` logger). Once the `"fastretry"` logger or any of its ancestors has
handlers, the built-in handler is **not** installed and your
configuration is used as is. The decision is taken on the first log
message, so configure `logging` during application startup.

To keep the package completely silent until you configure `logging`.

```python
from fastretry import config

config.logging(install_default_handler=False)
```

Each log kind has its own level:

```python
from fastretry import config
from fastretry.logging import LogLevel

config.logging(
    level_success=LogLevel.OFF,
    level_retry=LogLevel.WARNING,
    level_failure=LogLevel.ERROR,
    level_sleep=LogLevel.OFF,
    traceback_min_level=LogLevel.ERROR,
)
```

Set a level to `LogLevel.OFF` to disable that kind.

## Failure handling

When all attempts fail:

- If `return_default_value` is provided, the wrapper returns it.
- Otherwise, the wrapper raises an `ExceptionGroup` containing every
  exception from every attempt, in order.

```python
try:
    fetch()
except* ValueError as eg:
    for exc in eg.exceptions:
        ...
```

### Re-raise the single exception as is

Migration helper for code coming from `tenacity` or `backoff`, where
callers expect the original exception. Enable it globally:

```python
from fastretry import config

config.retry(unwrap_single_exception=True)
```

Now a failure with exactly one collected exception is re-raised
directly, so regular `except` blocks work:

```python
@retry(attempts=1)
def fetch() -> bytes: ...


try:
    fetch()
except ValueError:
    ...
```

Two or more collected exceptions still produce an exception group.

Exceptions that do **not** match `retry_on` (or match `no_retry_on`)
are not retried and propagate immediately. With the default
configuration, this includes `KeyboardInterrupt`, `SystemExit`, and
`asyncio.CancelledError`.

## Development

This project uses `uv` for dependency management and `just` as a task runner.

### Prerequisites

Install `uv` and `just`:

```bash
# uv (Python package manager)
pip install uv

# just (task runner)
uv tool install rust-just
```

### Common Commands

All development tasks are available via `just`. Run `just` without arguments to see the full list.

```bash
just ci             # run all checks (used by CI)
just check          # run all linters and type checks
just format         # format code with ruff
just format-check   # format code without modifying with ruff
just ruff           # lint with ruff
just mypy           # type check with mypy
just pyrefly        # type check with pyrefly
just test           # run tests with coverage
just test-fast      # run tests without coverage (fast)
just benchmark      # run the micro-benchmarks
just docs           # build documentation locally
just docs-no-warn   # build documentation locally without failing on warnings
just build          # build wheel and sdist
just sync           # sync dependencies
just update         # update dependencies
just clean          # clean build artifacts and caches
```

### Pre-commit hooks

The project uses `pre-commit` to run checks before each commit:

```bash
uv run pre-commit install
```

After installation, `ruff`, `mypy`, `pyrefly`, and other hooks will run automatically on `git commit`.
