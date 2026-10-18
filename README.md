# fastretry

[![test](https://github.com/MIXgleb/fastretry/actions/workflows/ci.yml/badge.svg)](https://github.com/MIXgleb/fastretry/actions/workflows/ci.yml)
$coverage$
[![Python](https://img.shields.io/pypi/pyversions/fastretry)](https://pypi.org/project/fastretry/)
[![PyPI](https://img.shields.io/pypi/v/fastretry)](https://pypi.org/project/fastretry/)


Retry decorator for synchronous and asynchronous functions.

- Sync and async functions, selected automatically.
- Fixed or exponential backoff, with optional jitter.
- Lifecycle callbacks for success, retry, and failure.
- Configurable per decorator or globally.
- Run sync functions in an executor from async code.
- 100% test coverage.

## Installation

```bash
pip install fastretry
```

## Usage

### Sync function

```python
from fastretry import retry


@retry(attempts=3, delay=1.0)
def fetch() -> bytes: ...
```

### Async function

```python
from fastretry import retry


@retry(attempts=3, delay=1.0)
async def fetch() -> bytes: ...
```

### Sync function, called asynchronously

Use `retry_async` to run a sync function in an executor so the event
loop is not blocked. The decorator always returns a coroutine function.

```python
from fastretry import retry_async


@retry_async(attempts=3, delay=1.0)
def blocking_io() -> bytes: ...


async def main() -> None:
    data = await blocking_io()
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
from fastretry import retry, ExponentialDelay


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
def fetch() -> bytes | None: ...
```

When all attempts fail, the wrapper returns `return_default_value`
instead of raising.

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
from fastretry import RetryStats, retry


def on_retry(stats: RetryStats) -> None:
    print(f"attempt {stats.attempt.retry_index} failed: {stats.attempt.last_exception!r}")


@retry(attempts=3, callbacks={"on_retry": on_retry})
def fetch() -> bytes: ...
```

Available keys: `on_success`, `on_retry`, `on_failure`. Callbacks may be
sync or async. Pass `None` for a key to disable that callback, or pass
`callbacks=None` to disable all of them.

## Configuration

Global defaults apply to all subsequently created decorators.

```python
from fastretry import LogLevel, config

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
named `"retry"`, which writes to stdout (falling back to stderr) by
default.

Each log kind has its own level:

```python
from fastretry import LogLevel, config

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

Exceptions that do **not** match `retry_on` (or match `no_retry_on`)
are not retried and propagate immediately. With the default
configuration, this includes `KeyboardInterrupt`, `SystemExit`, and
`asyncio.CancelledError`.
