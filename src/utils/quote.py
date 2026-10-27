"""Formatting for referencing a line range in a preview.

The payload is intentionally not translated: it is a path and a line range that
a person pastes into a chat to point at the source, not UI text.
"""

from __future__ import annotations


def format_line_reference(file_path: str, first_line: int, last_line: int) -> str:
    """Return ``path:line`` or ``path:first-last`` for a 1-based range."""
    if first_line == last_line:
        return f"{file_path}:{first_line}"
    return f"{file_path}:{first_line}-{last_line}"
