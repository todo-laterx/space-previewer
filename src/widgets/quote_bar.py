"""Floating copy bar shared by the text and Markdown previewers.

The bar never grabs focus or reflows content: it floats over the viewer, shows
the selected line range, and calls back into the viewer to copy either plain
lines or a paste-ready quote.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from utils.i18n import _

logger = logging.getLogger(__name__)

_CSS_INSTALLED = False

QUOTE_BAR_CSS = """
.quote-card {
    padding: 6px 8px 6px 12px;
    border-radius: 12px;
    background-color: @view_bg_color;
    border: 1px solid @borders;
    box-shadow: 0 2px 8px alpha(black, 0.18);
}
.quote-card label {
    font-size: 12px;
}
"""


def ensure_quote_bar_css() -> None:
    """Install the floating card style once per display."""
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(QUOTE_BAR_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_INSTALLED = True


class QuoteBar(Gtk.Box):
    """Compact range label with Copy and Copy reference actions."""

    def __init__(self, on_copy):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ensure_quote_bar_css()

        self._on_copy = on_copy
        self._timeout_id = None

        self.add_css_class("card")
        self.add_css_class("quote-card")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(18)
        self.set_visible(False)

        self.lbl_range = Gtk.Label()
        self.lbl_range.add_css_class("dim-label")
        self.lbl_range.set_margin_end(6)
        self.append(self.lbl_range)

        self.btn_copy = Gtk.Button(label=_("Copy"))
        self.btn_copy.add_css_class("flat")
        self.btn_copy.set_can_focus(False)
        self.btn_copy.set_tooltip_text(_("Copy the selected lines"))
        self.btn_copy.connect("clicked", lambda *_: self._copy(reference=False))
        self.append(self.btn_copy)

        self.btn_reference = Gtk.Button(label=_("Copy reference"))
        self.btn_reference.add_css_class("suggested-action")
        self.btn_reference.set_can_focus(False)
        self.btn_reference.set_tooltip_text(
            _("Copy the file path and line range")
        )
        self.btn_reference.connect("clicked", lambda *_: self._copy(reference=True))
        self.append(self.btn_reference)

    def set_lines(self, first_line: int, last_line: int) -> None:
        """Show the bar for a 1-based, inclusive line range."""
        if first_line == last_line:
            self.lbl_range.set_text(_("Line {number}").format(number=first_line))
        else:
            self.lbl_range.set_text(
                _("Lines {first}–{last}").format(first=first_line, last=last_line)
            )
        self.set_visible(True)

    def hide_bar(self) -> None:
        self.set_visible(False)

    def _copy(self, reference: bool) -> None:
        try:
            self._on_copy(reference)
        except Exception:
            logger.exception("Copy callback failed")

    def flash(self, reference: bool) -> None:
        """Briefly confirm a copy for the button the user pressed."""
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None
        self._reset_labels()
        button = self.btn_reference if reference else self.btn_copy
        button.set_label(_("Copied!"))
        self._timeout_id = GLib.timeout_add(1400, self._reset_timeout)

    def _reset_labels(self) -> None:
        self.btn_copy.set_label(_("Copy"))
        self.btn_reference.set_label(_("Copy reference"))

    def _reset_timeout(self) -> bool:
        self._timeout_id = None
        self._reset_labels()
        return False

    def teardown(self) -> None:
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None
        self._on_copy = None
