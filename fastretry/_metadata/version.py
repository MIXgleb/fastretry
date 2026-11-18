"""Lazily resolved package version."""

from functools import (
    cache,
)
from typing import (
    Final,
)

_PACKAGE_NAME: Final[str] = "fastretry"
"""Distribution name used to look up the installed version."""

_FALLBACK_VERSION: Final[str] = "0.0.0"
"""Version reported when the package metadata is not available."""


@cache
def _resolve_version() -> str:
    """
    Read the version from the installed package metadata.

    ``importlib.metadata`` is imported inside the function and not at module
    level on purpose: importing it and scanning ``sys.path`` takes tens of
    milliseconds, which would dominate the import time of the package.

    Returns
    -------
    str
        Version from the package metadata, or ``"0.0.0"`` when the package is
        used from a source tree without being installed.

    """
    from importlib import metadata  # ruff: ignore[import-outside-top-level]

    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return _FALLBACK_VERSION


def __getattr__(name: str) -> str:
    if name == "__version__":
        return _resolve_version()

    msg = f"module {_PACKAGE_NAME!r} has no attribute {name!r}"
    raise AttributeError(msg)
