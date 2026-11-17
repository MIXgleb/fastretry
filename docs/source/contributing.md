# Contributing

Bug reports, feature requests and pull requests are welcome on
[GitHub](https://github.com/MIXgleb/fastretry/issues). The project is small and
deliberately opinionated, so please open an issue before working on anything
that changes the public API.

The development setup is described in the README, which this page reuses:

## Development

```{include} ../../README.md
:start-after: Development
```

## Tests

The suite lives in `tests/` and must stay at **100 % coverage** — both the
package and the tests themselves are measured, and `--cov-fail-under=100` makes
a local `pytest` run fail otherwise:

```bash
uv run pytest              # full run with coverage
uv run pytest --no-cov     # quick run without coverage
uv run pytest -k version   # a single group of tests
```

`pytest-randomly` shuffles the order of tests, and `--strict-markers` with
`--strict-config` means that a new test must not depend on the order of the
others or use an undeclared marker. Global state configured through
`fastretry.config` is reset by an autouse fixture in `tests/conftest.py`.

## Documentation

The documentation is built with Sphinx from `docs/source`; Markdown pages use
MyST, and the README is included into the index page, so it is the first thing
to update when behavior changes:

```bash
just docs           # build with -W: warnings fail the build
just docs-no-warn   # build without failing, for debugging
```

```bash
uv run sphinx-build -W --keep-going -b html docs/source docs/build/html
```

The output is written to `docs/build/html`; open `docs/build/html/index.html`.

## Changelog

Every user-visible change gets an entry in {doc}`changelog`, in the section of
the version being prepared (`## [Unreleased]` or the upcoming release), under
one of `Added`, `Changed`, `Fixed` or `Tests`. Breaking changes are marked with
a **Breaking:** prefix.

## Releasing

Releases are cut from a tag: pushing `v*.*.*` triggers the `Publish` workflow,
which builds the distribution, checks it with `twine`, publishes to TestPyPI and
then to PyPI through trusted publishing. Before tagging:

1. bump `version` in `pyproject.toml`;
2. move the `[Unreleased]` entries under the new version with a date;
3. make sure `just ci` is green and the docs build without warnings.
