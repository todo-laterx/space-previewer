"""Translation helpers for Space Previewer.

Locale resolution follows gettext: ``LANGUAGE`` first, then ``LC_ALL``,
``LC_MESSAGES`` and ``LANG``. ``SPACE_PREVIEWER_LANG`` overrides all of them
and is useful for tests and screenshots.

Compiled catalogs are read from ``locale/`` next to the source tree or next to
the installed application directory. Missing catalogs fall back to the English
source strings without raising.
"""

from __future__ import annotations

import gettext as _gettext
import locale
import os
from pathlib import Path

DOMAIN = "space-previewer"

_translation: _gettext.NullTranslations | None = None


def _catalog_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "locale",  # repository checkout
        here.parents[1] / "locale",  # installed application directory
        Path.home() / ".local" / "share" / "space-previewer" / "locale",
    ]
    return [path for path in candidates if path.is_dir()]


def init_locale() -> _gettext.NullTranslations:
    """Initialise and cache the translation catalog."""
    global _translation
    if _translation is not None:
        return _translation

    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    override = os.environ.get("SPACE_PREVIEWER_LANG")
    languages = [override] if override else None

    for directory in _catalog_dirs():
        try:
            _translation = _gettext.translation(
                DOMAIN,
                localedir=str(directory),
                languages=languages,
                fallback=False,
            )
            return _translation
        except FileNotFoundError:
            continue

    _translation = _gettext.NullTranslations()
    return _translation


def gettext(message: str) -> str:
    return init_locale().gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return init_locale().ngettext(singular, plural, n)


_ = gettext
