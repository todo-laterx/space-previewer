"""Tests for the line-range quote payload; no GTK required."""

from __future__ import annotations

import pytest

from utils import quote


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("/tmp/a.py", "python"),
        ("/tmp/A.PY", "python"),
        ("/tmp/view.tsx", "tsx"),
        ("/tmp/notes.md", "markdown"),
        ("/tmp/run.zsh", "bash"),
        ("/tmp/data.unknown", ""),
        ("/tmp/README", ""),
    ],
)
def test_quote_language_for_path(path, language):
    assert quote.quote_language_for_path(path) == language


def test_single_line_quote():
    assert quote.format_line_quote("/tmp/a.py", 12, 12, "print('hi')") == (
        "/tmp/a.py:12\n\n```python\nprint('hi')\n```\n"
    )


def test_range_quote_keeps_trailing_newline_once():
    payload = quote.format_line_quote("/tmp/a.py", 12, 14, "a = 1\nb = 2\n")
    assert payload == "/tmp/a.py:12-14\n\n```python\na = 1\nb = 2\n```\n"
    assert not payload.endswith("\n\n```\n")


def test_unknown_extension_uses_plain_fence():
    payload = quote.format_line_quote("/tmp/data.bin", 1, 2, "x\ny")
    assert "```\n" in payload
    assert "```python" not in payload


def test_empty_text_still_forms_a_valid_block():
    assert quote.format_line_quote("/tmp/a.py", 3, 3, "") == (
        "/tmp/a.py:3\n\n```python\n\n```\n"
    )
