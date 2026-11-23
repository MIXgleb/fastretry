# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `max_time` option (also a global default) bounding the total time of one
  call, in seconds. The budget includes the delays, a retry that could not
  start within the remaining budget is not scheduled, and
  `AttemptState.deadline_reached` reports the outcome to callbacks and
  introspection.
- `resolve_fname()` (internal) as the single resolver of a call name, shared by
  the wrappers and the introspection lookups.

### Changed

- An aborted retry re-raises `KeyboardInterrupt`, `SystemExit`,
  `GeneratorExit` and `asyncio.CancelledError` unchanged, even when
  `return_default_value` is set. They are no longer wrapped in a
  `BaseExceptionGroup`, which left `asyncio` tasks uncancelled and broke
  `asyncio.timeout()`, `asyncio.wait_for()` and `Task.cancel()`.

### Fixed

- `config.logging(...)` no longer accepts retry options (and `config.retry(...)`
  no longer accepts logging options); a rejected call changes nothing.
- `delay=nan`/`inf`, and `ExponentialDelay` fields that are not finite numbers
  or not numbers at all, are rejected when the decorator is applied instead of
  raising from `time.sleep()` inside the retry loop. `attempts` and `delay`
  reject `bool`.
- A decorator applied to a `functools.partial` or to an instance of a callable
  class is now registered under the name the introspection lookups resolve, so
  `is_retrying()`/`get_stats_for()` find the run.
- A callable whose `__call__` is `async` is awaited instead of being treated as
  a sync callable (which returned an un-awaited coroutine and retried nothing).
- `ExponentialDelay` applies `max_delay` before the exponent overflows.
- A falsy callable object is used as a callback instead of being replaced by the
  no-op callback.
- The built-in console handler no longer overwrites a logger level set by the
  application, and `Log.record()` reports a record the logger filters out, so a
  swallowed callback error is warned about instead of being lost.
- `SharedLoop.run_callback()` reports a loop stopped by ``shutdown()`` as the
  documented `RuntimeError`, not as `ValueError: coroutine already executing`.

## [0.7.0] - 2026-11-17

### Added

- `Documentation` entry in `[project.urls]`, so the PyPI project page links to
  the Read the Docs site instead of the source repository.
- `config.logging(install_default_handler=...)` option to disable the built-in
  console handler and keep the package silent until the application configures
  `logging`.
- Global option `config.retry(unwrap_single_exception=True)` to re-raise a
  single collected exception as is instead of wrapping it in an exception
  group. Two or more collected exceptions are still raised as a group.
- Global option `config.retry(async_callback_mode=...)` selecting how async
  callbacks of sync functions are dispatched: `"thread_per_call"` (default,
  a thread with its own event loop per callback invocation), and
  `"shared_loop_when_running"` / `"shared_loop_always"` (a process-wide shared
  loop, about 30x less overhead per callback).
- Async callbacks executed in a per-call thread now receive the caller's
  `contextvars`.
- `RetryStats.attempt` now exposes `attempt_started_at`, `attempt_duration`
  (duration of the current attempt, callbacks and delays excluded) and
  `attempt_durations` (durations of every finished attempt).
- `fastretry.__version__` with the installed version. It is resolved lazily
  from the package metadata, so `import fastretry` does not pay for
  `importlib.metadata`.
- Documentation: cookbook, migration guide from tenacity/backoff/retry,
  benchmarks page with `benchmarks/benchmark.py`, contributing guide and the
  changelog page in Sphinx.

### Changed

- **Breaking:** `RetryStats.attempt.elapsed` is renamed to `total_elapsed`; the
  built-in log format and `log_extra` use `total_elapsed` as well.
- **Breaking:** the `sync_sleep_call` and `async_sleep_call` global options are
  removed from `config.retry(...)`.
- **Breaking:** the `sleep_call` argument is removed from the `SyncRetrying` and
  `AsyncRetrying` classes. Delays are now always slept with `time.sleep` in
  synchronous retries and `asyncio.sleep` in asynchronous ones, so a custom
  sleep function can no longer be passed.
- **Breaking:** `attempts` and `delay` of the `SyncRetrying` and `AsyncRetrying`
  classes are now read-only properties instead of attributes. They expose the
  effective values after validation (an `attempts` below 1 becomes 1, a
  negative fixed `delay` becomes 0) and can no longer be assigned after
  construction.
- Logging no longer touches global `logging` state at import time. The built-in
  console handler is created lazily on the first log message, writes to
  `sys.stderr`, and is installed only when the application has not configured
  `logging`.
- `return_default_value` is now typed statically: the decorated callable's
  return type is widened with the type of the default value (`R | D`). The
  runtime `UserWarning` for a type mismatch was removed together with the
  internal `TypeChecker` helper.

### Fixed

- `retry_async` no longer wraps an already asynchronous function into a second
  coroutine.
- Decorating an async function with options no longer collapses the signature to
  `Never`.

### Tests

- Documentation is built in CI with `-W --keep-going` in a separate `docs` job,
  so a broken cross-reference or a docstring that Sphinx cannot parse fails the
  pull request instead of the release.

## [0.6.1] - 2026-10-20

### Added

- `pre-commit` configuration and hooks for `ruff`, `mypy`, `pyrefly`, and other checks.
- `update-pre-commit.yml` workflow for automatic hook updates.
- `justfile` with common development tasks (`format`, `lint`, `test`, `docs`, `build`, etc.).
- Renovate configuration (`renovate.json`) for automated dependency updates, replacing Dependabot.
- Read the Docs (RTD) configuration (`.readthedocs.yaml`) and project setup.

### Changed

- **Breaking (docs):** moved documentation from GitHub Pages to Read the Docs. GitHub Pages and `docs.yml` workflow removed.
- Removed Dependabot configuration and its auto-merge workflow.
- Improved warning messages for type mismatch in `return_default_value` and swallowed exceptions in callbacks.

### Fixed

- Documentation API reference now lists `retry` and `retry_async` first, before other symbols.

## [0.6.0] - 2026-10-19

### Added

- Sphinx documentation under `docs/source/`:
  - `conf.py` — Sphinx configuration (Furo theme, napoleon, MyST, autodoc).
  - `index.md` — landing page, includes `README.md` via MyST.
  - `api.md` — API reference generated from docstrings.
- Documentation builds cleanly with `-W` (warnings as errors).
- `docs` dependency group to `pyproject.toml`.
- `docs.yml` — builds Sphinx docs on push/PR to `main`, deploys to GitHub Pages on push to `main` via `actions/deploy-pages`.
- `coverage-badge.yml` — separate workflow that runs tests on Python 3.13, generates `coverage.json`, and updates the coverage badge in `README.md` via `H3nSte1n/coverage-badge-creator`. Runs only on `push` to `main` to avoid concurrent commits from the test matrix.

### Changed

- `ci.yml` — removed `contents: write`, `persist-credentials`, and the `Update coverage badge` step. Tests no longer write to the repository.
- `dependabot.yml` — daily updates for GitHub Actions and `uv` dependencies at 02:00 UTC.
- `.gitignore` — added `coverage.json`

## [0.5.3] - 2026-10-18

### Added

- Coverage badge generation via `H3nSte1n/coverage-badge-creator`
  in CI, with the badge committed to `README.md` automatically.
- Dependabot configuration for automated updates of GitHub Actions and
  `uv` dependencies, with auto-merge for patch and minor updates.

### Changed

- `README.md` rewritten with installation, usage examples, options
  reference, and configuration guide.
- All keys in `TypedDict` definitions are now `ReadOnly`, preventing
  accidental mutation.

### Tests

- Added tests verifying that all `TypedDict` keys are `ReadOnly`.

## [0.5.1] - 2026-10-16

### Fixed

- CI/CD pipeline fixes for Trusted Publishing.

## [0.5.0] - 2026-10-16

### Added

- `uv` as the project's package manager, with a committed `uv.lock` for
  reproducible installs.
- `README.md` with installation and usage examples.
- GitHub Actions `CI` workflow: lint, format check, type check, and tests
  across supported Python versions.
- GitHub Actions `Publish` workflow: build, publish to TestPyPI, then
  publish to PyPI via Trusted Publishing.
- `[tool.uv]` configuration in `pyproject.toml`.

### Changed

- **Breaking:** minimum supported Python version raised to 3.13.

## [0.4.0] - 2026-10-16

### Added

- `_compat` package: version-gated imports for typing constructs and
  shared type aliases.
- `LICENSE` file (MIT).
- `CHANGELOG.md`.

### Changed

- **Breaking:** renamed the project from `retry` to `fastretry`. The
  import path is now `fastretry` instead of `retry`.
- **Breaking:** renamed modules under `fastretry._utils` to drop the
  leading underscore: `_callbacks` → `callbacks`, `_delay` → `delay`,
  `_logs` → `logs`, `_stats` → `stats`, `_warnings` → `warnings`.
- **Breaking:** renamed `_unset.py` to `sentinels.py` and
  `_function_types.py` to `functions.py`.
- Internal `__init__` modules no longer re-export imports.
- Docstrings reformatted to be shorter and focused on purpose.

### Fixed

- Correct `stacklevel` in emitted warnings.

### Tests

- 100% test coverage, including branch coverage.

## [0.3.0] - 2026-10-15

### Added

- `retry_async` decorator: runs sync and coroutine functions
  asynchronously, always returning a coroutine function. Sync callables
  are executed in an executor so the event loop is not blocked.
- `executor` option for `retry_async`: pass a `concurrent.futures.Executor`
  instance to use a custom executor.
- Context variables are propagated to executor threads via
  `contextvars.copy_context`.
- `is_coroutine_function` helper with `TypeIs` narrowing.

### Changed

- `retry` dispatches sync functions to `SyncRetrying` and coroutine
  functions to `AsyncRetrying`. Use `retry_async` to run a sync function
  in an executor.
- `FunctionTypes` replaced with `TypeChecker`.
- `RetryKwargs` split into `RetryKwargs` and `RetryWithExecutorKwargs`.
- `TypedDict` definitions now use `closed=True` (via `typing_extensions`)
  to reject unknown keys at type-check time.
- Return type of `retry` and `retry_async` decorators changed from
  `Awaitable` to `CoroutineType` for more precise typing.

### Fixed

- All type checker errors reported by mypy and pyrefly.

### Tests

- 100% test coverage, including branch coverage.

## [0.2.0] - 2026-10-08

### Added

- `config.context` context manager for per-task / per-thread defaults.
- Global defaults via `config.retry(...)` and `config.logging(...)`.
- `ExponentialDelay` with backoff factor and max delay.
- Jitter strategies: `"none"`, `"full"`, `"equal"`, `"decorrelated"`.
- Lifecycle callbacks: `on_success`, `on_retry`, `on_failure`.
- Logging via a shared `"retry"` logger with per-kind levels.
- `RetryStats` passed to callbacks.

### Changed

- Failure raises an `ExceptionGroup` (or `BaseExceptionGroup`) instead of
  the last exception, so callers can inspect every attempt.

### Tests

- Full test suite with 100% coverage.

## [0.1.0] - 2026-10-01

### Added

- Initial release: `retry` decorator for sync and async functions.
- `SyncRetrying` and `AsyncRetrying` strategies.
- Configurable attempts, delay, retry conditions, and logging.
