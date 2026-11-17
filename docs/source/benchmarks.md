# Benchmarks

A retry decorator sits on the hot path of every call, so its own overhead has
to stay small. This page shows what the overhead of `fastretry` is, how it was
measured, and where it goes.

## How to reproduce

The benchmark script is in the repository and needs nothing but `fastretry`:

```bash
just benchmark
```

or, without `just`:

```bash
uv run python benchmarks/benchmark.py
```

To include the comparison rows, add the libraries on the fly — they are not
dependencies of the project:

```bash
uv run --with tenacity --with backoff python benchmarks/benchmark.py
```

Every case calls a function that returns `1`, `20 000` times per sample
(`1 000` for the executor case, which is orders of magnitude slower), and the
best of `5` samples is reported. The best sample is used instead of the mean,
because the minimum is the least affected by scheduler noise and garbage
collection pauses. Logging is disabled in every case, so the numbers are pure
wrapper cost.

## Results

Measured on Windows 11 (build 26100, Intel i5-1135G7), CPython 3.13.16,
`fastretry` 0.6.1, `tenacity` 9.2.1 and `backoff` 2.2.1. The values below are
the median of several runs; a single run on a busy machine can be twice as slow,
so treat the numbers as an order of magnitude and re-measure on your hardware
rather than comparing absolute values.

| Case | µs per call | vs plain call |
|---|---:|---:|
| plain call | 0.03 | 1x |
| `fastretry`, successful attempt | 5.5 | ~165x |
| `fastretry`, one retry then success | 9 | ~300x |
| `tenacity`, successful attempt | 14 | ~420x |
| `backoff`, successful attempt | 2.0 | ~60x |

| Async case | µs per await | vs plain await |
|---|---:|---:|
| plain `await` | 0.08 | 1x |
| `retry` over a coroutine function | 5.7 | ~70x |
| `retry_async` over a coroutine function | 5.9 | ~70x |
| `retry_async` over a sync function (executor) | 100 | ~1250x |

The baseline is a bare Python call (tens of nanoseconds), so the ratios are
large by construction: "165x" means "about 5 µs of wrapper overhead per call",
not that a call became 165 times slower. Anything doing real work dwarfs it — a
single HTTP request or a database round trip is measured in milliseconds, three
orders of magnitude above the wrapper.

Two rows are worth reading twice:

- `retry` and `retry_async` cost the same on a coroutine function, because both
  await it directly. Use `retry` for coroutine functions; `retry_async` is for
  sync callables that must run in an executor.
- the executor is not free: every attempt of a sync callable under
  `retry_async` pays a thread hop of roughly 100 µs. It is the right tool for
  blocking I/O (which costs milliseconds anyway) and a poor fit for cheap
  pure-Python calls.

## Where the time goes

A `cProfile` run of 20 000 successful calls shows the overhead is dominated by
bookkeeping, not by the wrapped call:

- building the per-call `RetryStats` (a few `dataclasses.replace` calls and a
  fresh `AttemptState`) — roughly half of the profile;
- the default `on_success` callback (log record construction) — roughly a
  fifth; pass `callbacks=None` to skip it entirely (5.7 µs → 4.8 µs here).

The wrapper itself, the call of the wrapped function and the timing calls are
negligible next to that.

## Async callbacks of sync functions

An async callback attached to a **sync** function has to be executed in an
event loop of its own. When the calling thread already runs a loop, the default
`async_callback_mode="thread_per_call"` starts a thread with a fresh loop for
every callback, which costs milliseconds:

| `async_callback_mode` | µs per callback |
|---|---:|
| `"thread_per_call"` (default) | ~4500 |
| `"shared_loop_when_running"` | ~140 |
| `"shared_loop_always"` | ~100 |

Switching to one of the shared modes is a ~30x improvement for that path, at
the cost of serializing callbacks in one daemon thread (see the "Async
callbacks on sync functions" section of the README on the {doc}`index` page for
the trade-offs). The simplest fix is still to use a sync callback: it needs no
loop at all.
