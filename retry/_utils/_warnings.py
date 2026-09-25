"""Custom warning helpers with a ``disable_warnings`` toggle."""

import warnings


def warning(
    message: str,
    *,
    disable_warnings: bool,
    stacklevel: int,
) -> None:
    """
    Emit a warning unless warnings are disabled.

    Parameters
    ----------
    message : str
        Warning message.
    disable_warnings : bool
        If ``True``, the warning is suppressed.
    stacklevel : int
        Passed to :func:`warnings.warn`.

    """
    if not disable_warnings:
        warnings.warn(message, stacklevel=stacklevel)
