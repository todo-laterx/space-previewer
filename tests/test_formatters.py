"""Tests for locale-aware size and date formatting; no GTK required."""

from __future__ import annotations

import re

import pytest

from utils import formatters


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (int(2.5 * 1024 * 1024), "2.5 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
        (int(1.5 * 1024 * 1024 * 1024), "1.5 GB"),
    ],
)
def test_format_size_binary_thresholds(size_bytes, expected):
    assert formatters.format_size(size_bytes) == expected


def test_format_size_switches_to_kb_at_1024_bytes():
    assert formatters.format_size(1023).endswith(" B")
    assert formatters.format_size(1024).endswith(" KB")


def test_format_date_shape_for_fixed_timestamp():
    # 2023-11-14 22:13:20 UTC. Only the pattern is asserted because the local
    # timezone may shift the displayed value.
    formatted = formatters.format_date(1_700_000_000)

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", formatted)
