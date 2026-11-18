"""Configuration file for the Sphinx documentation builder."""

import logging
import pathlib
import sys
import tomllib
from typing import (
    Final,
    cast,
    override,
)

from sphinx.application import (
    Sphinx,
)

# -- Path setup --------------------------------------------------------------
_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent
"""Repository root: ``fastretry`` is imported from it and ``pyproject.toml`` is read from it."""

sys.path.insert(0, str(_ROOT))


def _get_project_meta() -> dict[str, object]:
    with (_ROOT / "pyproject.toml").open(mode="rb") as pyproject:
        return cast("dict[str, object]", tomllib.load(pyproject)["project"])


# -- Project information -----------------------------------------------------
project_meta = _get_project_meta()
project = str(project_meta["name"])
copyright = "2026, Gleb Mikhalev"
author = "Gleb Mikhalev"
release = str(project_meta["version"])

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "myst_parser",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = ["_templates"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
add_module_names = False

# -- autodoc -----------------------------------------------------------------
autodoc_default_options: dict[str, object] = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
    "exclude-members": "__dict__,__weakref__",
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# -- napoleon ----------------------------------------------------------------
napoleon_numpy_docstring = True
napoleon_use_param = True
napoleon_use_rtype = True

# -- MyST --------------------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]
html_title = "fastretry"

# -- Link checking -----------------------------------------------------------
nitpicky = True
nitpick_ignore = [
    ("py:meth", "asyncio.AbstractEventLoop.run_in_executor"),
    ("py:type", "fastretry._utils.callbacks.CallbackType"),
    ("py:class", "fastretry._decorators.retry._RetryDecorator"),
    ("py:class", "fastretry._decorators.retry._RetryDecoratorWithDefault"),
    ("py:class", "fastretry._decorators.retry_async._RetryAsyncDecorator"),
    ("py:class", "fastretry._decorators.retry_async._RetryAsyncDecoratorWithDefault"),
    ("py:class", "fastretry._utils.logs.Log"),
    ("py:class", "fastretry._utils.delays.WaitCallable"),
    ("py:class", "fastretry._utils.stats.DecoratorOptions"),
    ("py:class", "fastretry._utils.stats.GlobalOptions"),
    ("py:class", "fastretry._utils.stats.CallOptions"),
    ("py:class", "fastretry._utils.stats.AttemptState"),
    ("py:class", "fastretry._compat.sentinels.UnsetType"),
    ("py:class", "Log"),
    ("py:class", "DecoratorOptions"),
    ("py:class", "GlobalOptions"),
    ("py:class", "CallOptions"),
    ("py:class", "AttemptState"),
]


def setup(_: Sphinx) -> None:
    """Register the documentation build hooks."""
    exclude_warnings = (
        "duplicate object description of fastretry.callbacks.RetryCallbacks.on_success",
        "duplicate object description of fastretry.callbacks.RetryCallbacks.on_retry",
        "duplicate object description of fastretry.callbacks.RetryCallbacks.on_failure",
        "duplicate object description of fastretry.callbacks.RetryStats.log",
        "duplicate object description of fastretry.callbacks.RetryStats.decorator",
        "duplicate object description of fastretry.callbacks.RetryStats.global_options",
        "duplicate object description of fastretry.callbacks.RetryStats.call",
        "duplicate object description of fastretry.callbacks.RetryStats.attempt",
        "duplicate object description of fastretry.introspection.RetryStats.log",
        "duplicate object description of fastretry.introspection.RetryStats.decorator",
        "duplicate object description of fastretry.introspection.RetryStats.global_options",
        "duplicate object description of fastretry.introspection.RetryStats.call",
        "duplicate object description of fastretry.introspection.RetryStats.attempt",
        "duplicate object description of fastretry._utils.stats.RetryStats",
    )

    class _DupFilter(logging.Filter):
        @override
        def filter(self, record: logging.LogRecord) -> bool:
            message = record.getMessage()
            return not any(warn in message for warn in exclude_warnings)

    logging.getLogger("sphinx").addFilter(_DupFilter())
