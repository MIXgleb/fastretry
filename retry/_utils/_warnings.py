import warnings as _warnings


class Warnings:
    """
    Warning emitter that respects a ``disable_warnings`` flag.

    Wraps :func:`warnings.warn` and skips emission when warnings are
    disabled.

    Parameters
    ----------
    disable_warnings : bool
        If ``True``, all warnings are suppressed.

    """

    __slots__ = ("_disable_warnings",)

    def __init__(
        self,
        *,
        disable_warnings: bool,
    ) -> None:
        self._disable_warnings = disable_warnings

    def warn(
        self,
        message: str,
        *,
        stacklevel: int,
    ) -> None:
        """
        Emit a warning unless warnings are disabled.

        Parameters
        ----------
        message : str
            Warning message.
        stacklevel : int
            Passed to :func:`warnings.warn`.

        """
        if not self._disable_warnings:
            _warnings.warn(message, stacklevel=stacklevel)
