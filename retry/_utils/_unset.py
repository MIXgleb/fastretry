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
