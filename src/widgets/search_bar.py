"""Compact search bar hosted in the preview window's overlay card.

The bar owns no search logic. It exposes the entry, the match counter and the
navigation buttons, and calls back into the viewer that created it.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from utils.i18n import _

logger = logging.getLogger(__name__)


class SearchBar(Gtk.Box):
    """Search entry with match counter, case toggle and close button."""

    def __init__(self, on_changed, on_next, on_prev, on_close):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("code-search-bar")

        self._on_changed = on_changed
        self._on_next = on_next
        self._on_prev = on_prev
        self._on_close = on_close

        self.entry = Gtk.SearchEntry()
        self.entry.add_css_class("search-entry-flat")
        self.entry.set_placeholder_text(_("Find in file... (Enter to find next)"))
        self.entry.set_hexpand(False)
        self.append(self.entry)

        self.lbl_count = Gtk.Label(label="")
        self.lbl_count.add_css_class("search-count-label")
        self.append(self.lbl_count)

        self.btn_prev = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.btn_prev.add_css_class("code-btn-small")
        self.btn_prev.set_tooltip_text(_("Previous match (Shift+Enter)"))
        self.btn_prev.connect("clicked", lambda *_: self._on_prev())
        self.append(self.btn_prev)

        self.btn_next = Gtk.Button.new_from_icon_name("go-down-symbolic")
        self.btn_next.add_css_class("code-btn-small")
        self.btn_next.set_tooltip_text(_("Next match (Enter)"))
        self.btn_next.connect("clicked", lambda *_: self._on_next())
        self.append(self.btn_next)

        self.btn_case = Gtk.ToggleButton(label="Aa")
        self.btn_case.add_css_class("code-btn-small")
        self.btn_case.set_tooltip_text(_("Match Case"))
        self.btn_case.connect("toggled", lambda *_: self._on_changed())
        self.append(self.btn_case)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)

        self.btn_close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.btn_close.add_css_class("code-btn-small")
        self.btn_close.set_tooltip_text(_("Close Search (Esc)"))
        self.btn_close.connect("clicked", lambda *_: self._on_close())
        self.append(self.btn_close)

        self.entry.connect("search-changed", lambda *_: self._on_changed())
        self.entry.connect("activate", lambda *_: self._on_next())
        self.entry.connect("next-match", lambda *_: self._on_next())
        self.entry.connect("previous-match", lambda *_: self._on_prev())
        self.entry.connect("stop-search", lambda *_: self._on_close())

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.entry.add_controller(key_controller)

    def _on_key_pressed(self, controller, keyval, keycode, state) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                self._on_prev()
            else:
                self._on_next()
            return True
        if keyval == Gdk.KEY_Escape:
            self._on_close()
            return True
        return False

    def query(self) -> str:
        return self.entry.get_text()

    def set_query(self, text: str) -> None:
        self.entry.set_text(text or "")

    def case_sensitive(self) -> bool:
        return self.btn_case.get_active()

    def focus_entry(self) -> None:
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def set_count(self, text: str) -> None:
        self.lbl_count.set_text(text or "")

    def set_placeholder(self, text: str) -> None:
        self.entry.set_placeholder_text(text)
