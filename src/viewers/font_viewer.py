import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
from gi.repository import GLib, Gtk, Pango

from utils.formatters import format_size
from utils.i18n import _

logger = logging.getLogger(__name__)

_STYLE_WORDS = (
    "ExtraLight",
    "UltraLight",
    "ExtraBold",
    "UltraBold",
    "SemiBold",
    "DemiBold",
    "Thin",
    "Light",
    "Regular",
    "Book",
    "Medium",
    "Bold",
    "Black",
    "Heavy",
    "Italic",
    "Oblique",
)

_STYLE_TOKEN_RE = re.compile("|".join(_STYLE_WORDS), re.IGNORECASE)
_STYLE_SUFFIX_RE = re.compile(
    "(?:" + "|".join(_STYLE_WORDS) + ")+$", re.IGNORECASE
)
_STYLE_DISPLAY = {
    "extralight": "Extra Light",
    "ultralight": "Ultra Light",
    "extrabold": "Extra Bold",
    "ultrabold": "Ultra Bold",
    "semibold": "Semi Bold",
    "demibold": "Demi Bold",
    "thin": "Thin",
    "light": "Light",
    "regular": "Regular",
    "book": "Book",
    "medium": "Medium",
    "bold": "Bold",
    "black": "Black",
    "heavy": "Heavy",
    "italic": "Italic",
    "oblique": "Oblique",
}


def _split_font_name(file_path: str) -> tuple[str, str]:
    """Derive a family and style name from the font file name.

    The viewer does not load the font into the document, so the file name is
    the metadata it already knows. Pango normalises the family part.
    """
    stem = os.path.splitext(os.path.basename(file_path))[0]
    family = stem
    style_part = ""

    if "-" in stem or "_" in stem:
        separator = "-" if "-" in stem else "_"
        head, tail = stem.rsplit(separator, 1)
        if head and _STYLE_SUFFIX_RE.fullmatch(tail):
            family, style_part = head, tail
    if not style_part:
        match = _STYLE_SUFFIX_RE.search(stem)
        if match is not None and match.start() > 0:
            family = stem[:match.start()]
            style_part = match.group(0)

    family = family.replace("_", " ").strip() or stem
    try:
        description = Pango.FontDescription.from_string(family)
        normalized = description.get_family()
        if normalized:
            family = normalized
    except Exception:
        logger.debug("Could not normalise font family %r", family, exc_info=True)

    if style_part:
        tokens = _STYLE_TOKEN_RE.findall(style_part)
        style = " ".join(
            _(_STYLE_DISPLAY.get(token.lower(), token)) for token in tokens
        )
    else:
        style = _("Regular")

    return family, style


class FontViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self._status_callback = None

        try:
            self._file_size = os.path.getsize(file_path)
        except OSError:
            self._file_size = None

        self._family, self._style = _split_font_name(file_path)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.content_box.set_margin_start(24)
        self.content_box.set_margin_end(24)
        self.content_box.set_margin_top(24)
        self.content_box.set_margin_bottom(24)
        self.scrolled.set_child(self.content_box)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_info = Gtk.Label(
            label=_("Font file • {size}").format(size=self._size_text())
        )
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)

        self.load_font_preview()

    def load_font_preview(self) -> None:
        font_name = os.path.splitext(os.path.basename(self.file_path))[0]

        title = Gtk.Label(label=font_name)
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        self.content_box.append(title)

        sample_pangram = _("The quick brown fox jumps over the lazy dog")
        sample_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789 !@#$%^&*()_+-=[]{}|;':\",./<>?"

        chars_label = Gtk.Label(label=sample_chars)
        chars_label.set_halign(Gtk.Align.START)
        chars_label.add_css_class("body")
        self.content_box.append(chars_label)

        sizes = [14, 18, 24, 36, 48]
        for s in sizes:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            size_tag = Gtk.Label(label=_("{size} pt").format(size=s))
            size_tag.add_css_class("caption")
            size_tag.add_css_class("dim-label")
            size_tag.set_halign(Gtk.Align.START)

            sample_lbl = Gtk.Label(label=sample_pangram)
            sample_lbl.set_halign(Gtk.Align.START)
            sample_lbl.set_wrap(True)
            # Custom font size style
            escaped_pangram = GLib.markup_escape_text(sample_pangram)
            sample_lbl.set_markup(
                f"<span size='{s*1024}'>{escaped_pangram}</span>"
            )

            box.append(size_tag)
            box.append(sample_lbl)
            self.content_box.append(box)

    # ------------------------------------------------------------- contract

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def _size_text(self) -> str:
        if self._file_size is None:
            return _("Unknown")
        return format_size(self._file_size)

    def get_status_items(self) -> list[tuple[str, str]]:
        return [
            (_("Family"), self._family),
            (_("Style"), self._style),
            (_("Size"), self._size_text()),
        ]

    def teardown(self) -> None:
        """Drop the window callback; this viewer owns no timers or streams."""
        self._status_callback = None
