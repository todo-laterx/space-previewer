"""One-line status bar used at the bottom of the preview window.

The bar carries a type badge, a row of ``label value`` metadata pairs, and a
right-aligned transient state. It never renders cards and never uses emoji or
decorative dots; the only chrome is a hairline top border supplied by CSS.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gdk, Gtk, Pango

_CSS_INSTALLED = False

STATUS_BAR_CSS = """
.status-bar {
    border-top: 1px solid @borders;
    padding: 0 12px;
}
"""


def ensure_status_bar_css() -> None:
    """Install the status bar stylesheet once per process."""
    global _CSS_INSTALLED

    if _CSS_INSTALLED:
        return

    display = Gdk.Display.get_default()
    if display is None:
        return

    provider = Gtk.CssProvider()
    provider.load_from_data(STATUS_BAR_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_INSTALLED = True


class StatusBar(Gtk.Box):
    """A 30 px status bar with type, metadata and transient state slots."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        ensure_status_bar_css()

        self.set_size_request(-1, 30)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.END)
        self.add_css_class("status-bar")

        self._type_label = Gtk.Label(label="")
        self._type_label.add_css_class("caption")
        self._type_label.add_css_class("dim-label")
        self._type_label.set_halign(Gtk.Align.START)
        self._type_label.set_valign(Gtk.Align.CENTER)
        self._type_label.set_visible(False)
        self.append(self._type_label)

        self._items_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self._items_box.set_halign(Gtk.Align.START)
        self._items_box.set_valign(Gtk.Align.CENTER)
        self._items_box.set_hexpand(True)
        self.append(self._items_box)

        self._state_label = Gtk.Label(label="")
        self._state_label.add_css_class("caption")
        self._state_label.add_css_class("dim-label")
        self._state_label.set_halign(Gtk.Align.END)
        self._state_label.set_valign(Gtk.Align.CENTER)
        self._state_label.set_visible(False)
        self.append(self._state_label)

    def set_type(self, text: str) -> None:
        """Set the leading type badge, for example ``CODE`` or ``PDF``."""
        self._type_label.set_text(text or "")
        self._type_label.set_visible(bool(text))

    def set_items(self, items: list[tuple[str, str]]) -> None:
        """Replace the metadata area with ``(label, value)`` pairs.

        Labels are dimmed and values use the normal caption color. Each value
        is ellipsized so the bar stays on one line.
        """
        child = self._items_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._items_box.remove(child)
            child = next_child

        for label_text, value_text in items or []:
            pair = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            pair.set_valign(Gtk.Align.CENTER)

            label = Gtk.Label(label=str(label_text))
            label.add_css_class("caption")
            label.add_css_class("dim-label")
            label.set_valign(Gtk.Align.CENTER)
            pair.append(label)

            value = Gtk.Label(label=str(value_text))
            value.add_css_class("caption")
            value.set_valign(Gtk.Align.CENTER)
            value.set_xalign(0.0)
            value.set_ellipsize(Pango.EllipsizeMode.END)
            value.set_max_width_chars(48)
            pair.append(value)

            self._items_box.append(pair)

    def set_state(self, text: str) -> None:
        """Set the right-aligned transient state, for example ``Loading...``."""
        self._state_label.set_text(text or "")
        self._state_label.set_visible(bool(text))

    def clear_state(self) -> None:
        """Clear the transient state slot."""
        self.set_state("")
