"""Sentinel type and value for "no value provided"."""

from typing import (
    Final,
    Literal,
    final,
    override,
)


@final
class UnsetType:
    """
    Sentinel type meaning "no value provided".

    Used instead of ``None`` to distinguish "user did not pass anything"
    from "user explicitly passed ``None``" (which may be a valid value).
    """

    __slots__ = ()

    @override
    def __repr__(self) -> Literal["<unset>"]:
        return "<unset>"


UNSET: Final[UnsetType] = UnsetType()
"""Singleton instance of :class:`UnsetType`."""
