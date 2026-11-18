"""Tests for the public API surface of the package."""

import importlib

import pytest

import fastretry

PUBLIC_MODULES = (
    "fastretry.callbacks",
    "fastretry.delays",
    "fastretry.introspection",
    "fastretry.logging",
)

RE_EXPORTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "fastretry.callbacks",
        "fastretry._utils.callbacks",
        (
            "RetryCallbacks",
            "default_on_failure",
            "default_on_retry",
            "default_on_success",
        ),
    ),
    (
        "fastretry.callbacks",
        "fastretry._utils.stats",
        ("RetryStats",),
    ),
    (
        "fastretry.delays",
        "fastretry._utils.delays",
        (
            "Delay",
            "ExponentialDelay",
            "WaitCallable",
        ),
    ),
    (
        "fastretry.introspection",
        "fastretry._utils.introspection",
        (
            "get_active_runs",
            "get_current_run_id",
            "get_current_stats",
            "get_stats_by_run_id",
            "get_stats_for",
            "is_retrying",
        ),
    ),
    (
        "fastretry.introspection",
        "fastretry._utils.stats",
        ("RetryStats",),
    ),
    (
        "fastretry.logging",
        "fastretry._utils.logs",
        (
            "FASTRETRY_LOGGER_NAME",
            "LogLevel",
        ),
    ),
)


def test_root_exports_core_api_only() -> None:
    """The root package exposes only the decorators and the global config."""
    assert set(fastretry.__all__) == {"config", "retry", "retry_async"}


@pytest.mark.parametrize("module_name", PUBLIC_MODULES)
def test_public_module_exports_every_listed_name(module_name: str) -> None:
    """Every name listed in ``__all__`` is present on the module."""
    module = importlib.import_module(module_name)

    assert module.__all__

    for name in module.__all__:
        assert hasattr(module, name), f"{module_name}.{name} is missing"


@pytest.mark.parametrize(("facade_name", "impl_name", "names"), RE_EXPORTS)
def test_facade_forwards_implementation(
    facade_name: str,
    impl_name: str,
    names: tuple[str, ...],
) -> None:
    """Facades re-export the very objects defined by the internal modules."""
    facade = importlib.import_module(facade_name)
    impl = importlib.import_module(impl_name)

    for name in names:
        forwarded = getattr(facade, name)

        assert forwarded is getattr(impl, name), f"{facade_name}.{name} is not forwarded"
