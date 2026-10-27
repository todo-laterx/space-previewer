"""Tests for the line-range reference payload; no GTK required."""

from __future__ import annotations

import pytest

from utils import quote


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        (12, 12, "/tmp/a.py:12"),
        (7, 19, "/tmp/a.py:7-19"),
        (1, 1, "/tmp/a.py:1"),
    ],
)
def test_line_reference(first, last, expected):
    assert quote.format_line_reference("/tmp/a.py", first, last) == expected


def test_reference_has_no_trailing_whitespace():
    payload = quote.format_line_reference("/tmp/a.md", 3, 5)
    assert payload == "/tmp/a.md:3-5"
    assert not payload.endswith("\n")
