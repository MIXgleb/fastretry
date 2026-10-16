# fastretry

Retry decorator for synchronous and asynchronous functions.

## Installation

```bash
pip install fastretry
```

## Usage

```python
from fastretry import retry


@retry(attempts=3, delay=1.0)
def fetch() -> bytes: ...
```