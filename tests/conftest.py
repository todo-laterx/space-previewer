"""Shared pytest setup for tests that do not need GTK.

The application imports its modules as top-level packages from ``src/``
(``utils.*``, ``viewers.*``). Put that directory on ``sys.path`` and pin the
environment so size and date formatting are deterministic on any machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# The translation helper reads these on first use; keep catalogs and number
# formatting predictable regardless of the developer's desktop locale.
os.environ["SPACE_PREVIEWER_LANG"] = "en"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

# Keep the test run from writing bytecode into the source tree.
sys.dont_write_bytecode = True
