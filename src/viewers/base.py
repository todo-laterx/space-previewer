"""Shared viewer contract and lifecycle helpers.

Viewers are duck-typed. They do not have to inherit from a common base class,
which keeps third-party plugins free to use a plain ``Gtk.Box`` (or any other
widget). :class:`ViewerProtocol` documents the optional members the window and
dispatcher may probe; callers must still use ``hasattr``/``getattr`` because
the members are optional.

This module deliberately contains no GTK widget subclass.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ViewerProtocol(Protocol):
    """Optional duck-typed contract implemented by preview viewers.

    ``get_desired_size`` is required for viewers that the window sizes
    responsively. All other members are optional; a viewer exposes only the
    ones it actually supports.

    The protocol is runtime-checkable, but ``isinstance`` only verifies that
    the attribute exists, not that it has the documented signature.
    """

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        """Return the preferred ``(width, height)`` for the preview window."""
        ...

    def teardown(self) -> None:
        """Stop owned resources: players, timers, threads, network requests."""
        ...

    def get_header_controls(self) -> list[Any]:
        """Return at most three widgets to place in the application header."""
        ...

    def get_status_items(self) -> list[tuple[str, str]]:
        """Return ``(label, value)`` pairs for the one-line status bar."""
        ...

    def toggle_search(self) -> None:
        """Show or hide the viewer's in-file search overlay."""
        ...

    def is_search_open(self) -> bool:
        """Return whether the in-file search overlay is currently open."""
        ...

    def close_search(self) -> None:
        """Close the in-file search overlay and restore focus."""
        ...


def teardown_viewer(viewer: Any) -> None:
    """Call ``viewer.teardown()`` when present, never raising.

    A third-party plugin may raise at any point, including from teardown. A
    failed cleanup must not take down the preview window or prevent the next
    viewer from being created, so errors are logged and swallowed.
    """
    if viewer is None:
        return

    try:
        teardown = getattr(viewer, "teardown", None)
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception(
            "Could not read teardown from viewer %s", type(viewer).__name__
        )
        return

    if not callable(teardown):
        return

    try:
        teardown()
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception(
            "Viewer teardown failed for %s", type(viewer).__name__
        )
