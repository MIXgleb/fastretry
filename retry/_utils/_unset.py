"""
Sentinel type for "no value provided".

Defines :class:`~retry._utils._unset.UnsetType` and the
:data:`~retry._utils._unset.UNSET` singleton, used across
the package to distinguish "user did not pass anything"
from an explicit ``None``.
"""

from typing import (
    Final,
    final,
    override,
)


@final
class UnsetType:
    """
    Sentinel type meaning "no value provided".

    Used instead of ``None`` to distinguish "user did not pass anything"
    from "user explicitly passed ``None``" (which may be a valid value,
    e.g. for ``return_default_value``).
    """

    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return "<unset>"


UNSET: Final[UnsetType] = UnsetType()
