"""Version-gated imports for typing constructs."""

__all__ = ("TypedDict", "is_typeddict")

import sys

if sys.version_info >= (3, 15):  # pragma: >=3.15 cover
    from typing import (
        TypedDict,
        is_typeddict,
    )
else:  # pragma: <3.15 cover
    from typing_extensions import (
        TypedDict,
        is_typeddict,
    )
