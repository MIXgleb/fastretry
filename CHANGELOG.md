# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

### Tests

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
