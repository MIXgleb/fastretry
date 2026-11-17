# API Reference

## Core Functions

```{eval-rst}
.. autofunction:: fastretry.retry

.. autofunction:: fastretry.retry_async
```

## Introspection

The retry in progress is visible from anywhere in the process:

- `fastretry.is_retrying()` — whether a retry loop is active in the current
  context, or, with a callable or a qualified name, anywhere in the process;
- `fastretry.get_current_stats()` — live `RetryStats` of the current run;
- `fastretry.get_current_run_id()` — process-wide id of the current run;
- `fastretry.get_stats_for()` and `fastretry.get_stats_by_run_id()` — look up
  active runs by function, qualified name, `asyncio.Task` or
  `functools.partial`, or by run id; both return the live `RetryStats`;
- `fastretry.get_active_runs()` — live stats of every run in progress.

See {doc}`cookbook` for examples.

## Version

The installed version is available as `fastretry.__version__`.

## Full API

```{eval-rst}
.. automodule:: fastretry
   :members:
   :show-inheritance:
   :exclude-members: retry, retry_async
```
