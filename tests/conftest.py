"""Shared fixtures for retry tests."""

from collections.abc import (
    Generator,
)

import pytest

from fastretry._configs.defaults import (
    context_defaults,
    global_defaults,
)
from fastretry._utils.shared_loop import (
    shared_loop,
)


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def _isolate_defaults() -> Generator[None]:
    """Isolate global and context defaults between tests."""
    token = context_defaults.set(None)
    global_defaults.reset()

    yield

    context_defaults.reset(token)
    global_defaults.reset()


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def _shutdown_shared_loop() -> Generator[None]:
    """Stop the process-wide callback loop after every test."""
    yield
    shared_loop.shutdown()
