# API Reference

Only the decorators and the global configuration are importable from the package
root; every other object is imported from the module of its feature.

## Core Functions

```{eval-rst}
.. autofunction:: fastretry.retry

.. autofunction:: fastretry.retry_async
```

## Introspection

The retry in progress is visible from anywhere in the process:

- `fastretry.introspection.is_retrying()` — whether a retry loop is active in the
  current context, or, with a callable or a qualified name, anywhere in the process;
- `fastretry.introspection.get_current_stats()` — live `RetryStats` of the current run;
- `fastretry.introspection.get_current_run_id()` — process-wide id of the current run;
- `fastretry.introspection.get_stats_for()` and
  `fastretry.introspection.get_stats_by_run_id()` — look up active runs by function,
  qualified name, `asyncio.Task` or `functools.partial`, or by run id; both return
  the live `RetryStats`;
- `fastretry.introspection.get_active_runs()` — live stats of every run in progress.

See {doc}`cookbook` for examples.

```{eval-rst}
.. automodule:: fastretry.introspection
   :members:
   :imported-members:
   :show-inheritance:
```

## Callbacks

```{eval-rst}
.. automodule:: fastretry.callbacks
   :members:
   :imported-members:
   :show-inheritance:
```

## Delays

```{eval-rst}
.. automodule:: fastretry.delays
   :members:
   :imported-members:
   :show-inheritance:
```

## Logging

```{eval-rst}
.. automodule:: fastretry.logging
   :members:
   :imported-members:
   :show-inheritance:
```

## Version

The installed version is available as `fastretry.__version__`.

## Full API

```{eval-rst}
.. automodule:: fastretry
   :members:
   :show-inheritance:
   :exclude-members: retry, retry_async
```
