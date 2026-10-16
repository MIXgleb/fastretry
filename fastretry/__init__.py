"""Retry decorator for synchronous and asynchronous functions."""

from fastretry._config import (
    config as config,
)
from fastretry._retry import (
    retry as retry,
)
from fastretry._retry import (
    retry_async as retry_async,
)
from fastretry._utils.callbacks import (
    RetryCallbacks as RetryCallbacks,
)
from fastretry._utils.callbacks import (
    default_on_failure as default_on_failure,
)
from fastretry._utils.callbacks import (
    default_on_retry as default_on_retry,
)
from fastretry._utils.callbacks import (
    default_on_success as default_on_success,
)
from fastretry._utils.delay import (
    ExponentialDelay as ExponentialDelay,
)
from fastretry._utils.logs import (
    LogLevel as LogLevel,
)
from fastretry._utils.stats import (
    RetryStats as RetryStats,
)
