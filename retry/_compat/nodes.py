"""Version-gated imports for typing constructs."""

__all__ = ("TypeIs", "TypedDict")

import sys

if sys.version_info >= (3, 15):  # pragma: >=3.15 cover
    from typing import (
        TypedDict,
    )
else:  # pragma: <3.15 cover
    from typing_extensions import (
        TypedDict,
    )

if sys.version_info >= (3, 13):  # pragma: >=3.13 cover
    from typing import (
        TypeIs,
    )
else:  # pragma: <3.13 cover
    from typing_extensions import (
        TypeIs,
    )
