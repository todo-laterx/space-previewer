#!/usr/bin/env python3
"""Install a Dolphin service menu pointing at this source checkout."""

import argparse
import os
from pathlib import Path


MENU_NAME = "space-previewer.desktop"
PROJECT_DIR = Path(__file__).resolve().parents[1]


def quote_exec_argument(value):
    # Exec quoting is not shell quoting. Escape field codes, then apply the
    # Exec string and desktop-entry string escaping layers in that order.
    value = str(value).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    value = '"' + value + '"'
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def render_menu(main_path):
    template = (PROJECT_DIR / "data" / MENU_NAME).read_text(encoding="utf-8")
    return template.replace(
        "Exec=/usr/bin/space-previewer ",
        f"Exec=/usr/bin/python3 {quote_exec_argument(main_path)} ",
    )


def menu_path():
    data_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(data_home) if data_home and Path(data_home).is_absolute() else Path.home() / ".local/share"
    return base / "kio/servicemenus" / MENU_NAME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="Remove only the Dolphin service menu")
    args = parser.parse_args()
    target = menu_path()
    if args.uninstall:
        target.unlink(missing_ok=True)
        print(f"Removed {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_menu(PROJECT_DIR / "src/main.py"), encoding="utf-8")
    # User service menus must be executable for Dolphin to trust them.
    target.chmod(0o755)
    print(f"Installed {target}")
    print("Keep this checkout in place. Reopen Dolphin to load the menu.")


if __name__ == "__main__":
    main()
