"""Repository hygiene checks that do not require GTK.

These guard against the junk files and generated artifacts that must never be
committed: editor debris at the repository root and compiled message catalogs
under ``src/``.

Bytecode caches are intentionally not checked: ``__pycache__`` is gitignored and
is created by the required ``compileall`` step, so asserting its absence would
fight the documented workflow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

JUNK_NAMES = ("B", "B[Space", "C[Markdown", "D[IDE]")


def test_no_junk_files_at_repository_root():
    found = [name for name in JUNK_NAMES if (REPO_ROOT / name).exists()]

    assert not found, f"Remove junk files from the repository root: {found}"


def test_no_gettext_catalogs_under_src():
    src = REPO_ROOT / "src"
    if not src.is_dir():
        pytest.skip("src/ is not present in this checkout")

    found = sorted(
        str(path.relative_to(REPO_ROOT)) for path in src.rglob("*.mo")
    )

    assert not found, f"Compiled gettext catalogs must not live under src/: {found}"
