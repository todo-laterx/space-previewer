"""Tests for MIME detection; no GTK or display server required."""

from __future__ import annotations

import pytest

from utils.mime_detector import CUSTOM_MIME, detect_mime_type


@pytest.mark.parametrize(("suffix", "expected"), sorted(CUSTOM_MIME.items()))
def test_custom_mime_extensions(tmp_path, suffix, expected):
    path = tmp_path / f"sample{suffix}"
    path.write_bytes(b"content")

    assert detect_mime_type(str(path)) == expected


def test_custom_mime_extension_is_case_insensitive(tmp_path):
    path = tmp_path / "SAMPLE.PY"
    path.write_bytes(b"print('hello')\n")

    assert detect_mime_type(str(path)) == "text/x-python"


def test_directory_returns_inode_directory(tmp_path):
    assert detect_mime_type(str(tmp_path)) == "inode/directory"


def test_unknown_extension_falls_back_to_text_content(tmp_path):
    path = tmp_path / "notes.spacepreviewerunknown"
    path.write_bytes(b"plain text without a known extension\n")

    assert detect_mime_type(str(path)) == "text/plain"


def test_binary_content_returns_octet_stream(tmp_path):
    path = tmp_path / "payload.spacepreviewerunknown"
    path.write_bytes(b"header\x00binary payload")

    assert detect_mime_type(str(path)) == "application/octet-stream"


def test_text_content_returns_plain_text(tmp_path):
    path = tmp_path / "README"
    path.write_bytes(b"line one\nline two\n")

    assert detect_mime_type(str(path)) == "text/plain"
