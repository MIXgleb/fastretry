# fastretry task runner.
# Run `just` to list available recipes.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Default recipe: list available recipes.
default:
    @just --list

# Run all linters and type checks
check: format ruff mypy pyrefly
    @echo "All checks passed"

# Run all CI checks: format, lint, typecheck, test, docs.
ci: format-check ruff mypy pyrefly test docs
    @echo "All checks passed"

# Format code with ruff.
format:
    uv run ruff format

# Check formatting without modifying files with ruff.
format-check:
    uv run ruff format --check

# Check lint without modifying files with ruff.
ruff:
    uv run ruff check

# Type check with mypy.
mypy:
    uv run mypy

# Type check with pyrefly.
pyrefly:
    uv run pyrefly check

# Run tests with coverage.
test:
    uv run pytest

# Run tests without coverage (fast).
test-fast:
    uv run pytest --no-cov

# Build documentation locally.
docs:
    uv run sphinx-build -W --keep-going -b html docs/source docs/build/html
    @echo "Docs built at docs/build/html/index.html"

# Build documentation without failing on warnings (for debugging).
docs-no-warn:
    uv run sphinx-build -b html docs/source docs/build/html

# Build the distribution (wheel + sdist).
build:
    uv build
    uv run twine check dist/*

# Update dependencies.
update:
    uv lock --upgrade

# Sync dependencies from uv.lock.
sync:
    uv sync --locked --dev --group docs

# Clean build artifacts and caches.
clean:
    @echo "Cleaning..."
    -Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build, *.egg-info
    -Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .pytest_cache, .mypy_cache, .ruff_cache, .coverage, htmlcov
    -Remove-Item -Recurse -Force -ErrorAction SilentlyContinue docs/build
    -Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    @echo "Done."
