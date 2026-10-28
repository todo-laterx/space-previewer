"""In-preview search for the rendered Markdown view.

The rendered document is a tree of labels and code views, not one text buffer,
so the search collects plain text per block, paints matches with Pango
attributes or buffer tags, and scrolls the preview column to the match.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango

from utils.i18n import _
from widgets.search_bar import SearchBar

logger = logging.getLogger(__name__)

MAX_MATCHES = 2000
MATCH_BG_LIGHT = 0xFFE08A
MATCH_BG_DARK = 0x6E5A12
CURRENT_BG_LIGHT = 0x9DBFF7
CURRENT_BG_DARK = 0x3867D6


def _rgb565(hex_value: int) -> tuple[int, int, int]:
    """Expand a 0xRRGGBB literal to the 16-bit channels Pango expects."""
    red = (hex_value >> 16) & 0xFF
    green = (hex_value >> 8) & 0xFF
    blue = hex_value & 0xFF
    return red * 257, green * 257, blue * 257


class MarkdownSearch:
    """Search over a rendered Markdown document, without leaving the preview."""

    def __init__(self, viewer, is_dark):
        self.viewer = viewer
        self._is_dark = is_dark
        self._open = False
        self._matches: list[dict] = []
        self._current = -1
        self.bar = SearchBar(
            on_changed=self._on_query_changed,
            on_next=self.next_match,
            on_prev=self.previous_match,
            on_close=self.close,
        )

    # ------------------------------------------------------------- lifecycle

    def is_open(self) -> bool:
        return self._open

    def widget(self):
        return self.bar

    def toggle(self) -> None:
        if not self._open:
            self._open = True
            self.bar.focus_entry()
            query = self.bar.query()
            if query:
                self._run_query(query)
            self.viewer._notify_search_state()
            return
        self.bar.focus_entry()

    def open_with_query(self, query: str) -> None:
        """Open the bar with a query carried over from the other mode."""
        if not self._open:
            self._open = True
        self.bar.entry.set_text(query or "")
        self.bar.focus_entry()
        if query:
            self._run_query(query)
        self.viewer._notify_search_state()

    def query(self) -> str:
        return self.bar.query()

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._clear_highlights()
        self._matches = []
        self._current = -1
        self.bar.set_count("")
        self.viewer.focus_preview()
        self.viewer._notify_search_state()

    def reset(self) -> None:
        """Drop stale matches after the document was re-rendered."""
        self._clear_highlights()
        self._matches = []
        self._current = -1
        self.bar.set_count("")

    # ------------------------------------------------------------- searching

    def _on_query_changed(self) -> None:
        self._run_query(self.bar.query())

    def _targets(self):
        """Yield ``(kind, widget, text)`` for every searchable block."""
        stack = [self.viewer.doc_box]
        while stack:
            widget = stack.pop()
            child = widget.get_last_child()
            # Depth-first in document order: push children reversed.
            children = []
            while child is not None:
                children.append(child)
                child = child.get_prev_sibling()
            if isinstance(widget, Gtk.Label):
                yield "label", widget, widget.get_text() or ""
            elif isinstance(widget, Gtk.TextView):
                buffer = widget.get_buffer()
                yield (
                    "buffer",
                    widget,
                    buffer.get_text(
                        buffer.get_start_iter(), buffer.get_end_iter(), True
                    ),
                )
            else:
                stack.extend(children)

    def _run_query(self, query: str) -> None:
        self._clear_highlights()
        self._matches = []
        self._current = -1

        if not query:
            self.bar.set_count("")
            return

        case_sensitive = self.bar.case_sensitive()
        needle = query if case_sensitive else query.casefold()

        for kind, widget, text in self._targets():
            haystack = text if case_sensitive else text.casefold()
            if len(haystack) != len(text):
                # casefold changed the length, so offsets cannot be mapped;
                # fall back to a literal match for this block.
                haystack = text
                needle = query
            start = 0
            while True:
                index = haystack.find(needle, start)
                if index < 0:
                    break
                self._matches.append(
                    {
                        "kind": kind,
                        "widget": widget,
                        "start": index,
                        "end": index + len(needle),
                    }
                )
                start = index + max(1, len(needle))
                if len(self._matches) >= MAX_MATCHES:
                    break
            if len(self._matches) >= MAX_MATCHES:
                break

        if not self._matches:
            self.bar.set_count(_("No matches"))
            return

        self._paint_all()
        self._current = 0
        self._show_current()

    def _paint_all(self) -> None:
        match_rgb = _rgb565(MATCH_BG_DARK if self._is_dark else MATCH_BG_LIGHT)
        by_label: dict[Gtk.Label, list[dict]] = {}
        for match in self._matches:
            if match["kind"] == "label":
                by_label.setdefault(match["widget"], []).append(match)

        for label, matches in by_label.items():
            attrs = Pango.AttrList()
            for match in matches:
                start = len((label.get_text() or "")[: match["start"]].encode("utf-8"))
                end = len((label.get_text() or "")[: match["end"]].encode("utf-8"))
                try:
                    attribute = Pango.attr_background_new(*match_rgb)
                except Exception:
                    logger.debug("Could not create a search attribute", exc_info=True)
                    continue
                attribute.start_index = start
                attribute.end_index = end
                attrs.insert(attribute)
            try:
                label.set_attributes(attrs)
            except Exception:
                logger.debug("Could not apply search attributes", exc_info=True)

        buffer_matches: dict[Gtk.TextView, list[dict]] = {}
        for match in self._matches:
            if match["kind"] == "buffer":
                buffer_matches.setdefault(match["widget"], []).append(match)

        for text_view, matches in buffer_matches.items():
            buffer = text_view.get_buffer()
            tag = buffer.get_tag_table().lookup("md-search")
            if tag is None:
                rgba = _rgba(MATCH_BG_DARK if self._is_dark else MATCH_BG_LIGHT)
                tag = buffer.create_tag("md-search", background_rgba=rgba)
            for match in matches:
                start = buffer.get_iter_at_offset(match["start"])
                end = buffer.get_iter_at_offset(match["end"])
                buffer.apply_tag(tag, start, end)

    def _clear_highlights(self) -> None:
        for match in self._matches:
            widget = match["widget"]
            if match["kind"] == "label":
                try:
                    if widget.get_attributes() is not None:
                        widget.set_attributes(None)
                except Exception:
                    logger.debug("Could not clear search attributes", exc_info=True)
            else:
                buffer = widget.get_buffer()
                for name in ("md-search", "md-search-current"):
                    tag = buffer.get_tag_table().lookup(name)
                    if tag is not None:
                        buffer.remove_tag(
                            tag, buffer.get_start_iter(), buffer.get_end_iter()
                        )

    def next_match(self) -> None:
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._show_current()

    def previous_match(self) -> None:
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._show_current()

    def _show_current(self) -> None:
        if not self._matches:
            return
        match = self._matches[self._current]
        self._paint_current(match)
        self.bar.set_count(
            _("{current} / {total}").format(
                current=self._current + 1, total=len(self._matches)
            )
        )
        self._scroll_to(match["widget"])

    def _paint_current(self, match: dict) -> None:
        # Clear the previous current highlight everywhere first.
        for item in self._matches:
            widget = item["widget"]
            if item["kind"] == "buffer":
                buffer = widget.get_buffer()
                tag = buffer.get_tag_table().lookup("md-search-current")
                if tag is not None:
                    buffer.remove_tag(
                        tag, buffer.get_start_iter(), buffer.get_end_iter()
                    )

        widget = match["widget"]
        if match["kind"] == "label":
            text = widget.get_text() or ""
            attrs = Pango.AttrList()
            match_rgb = _rgb565(MATCH_BG_DARK if self._is_dark else MATCH_BG_LIGHT)
            current_rgb = _rgb565(
                CURRENT_BG_DARK if self._is_dark else CURRENT_BG_LIGHT
            )
            for item in self._matches:
                if item["widget"] is not widget:
                    continue
                rgb = current_rgb if item is match else match_rgb
                start = len(text[: item["start"]].encode("utf-8"))
                end = len(text[: item["end"]].encode("utf-8"))
                attribute = Pango.attr_background_new(*rgb)
                attribute.start_index = start
                attribute.end_index = end
                attrs.insert(attribute)
            try:
                widget.set_attributes(attrs)
            except Exception:
                logger.debug("Could not paint the current match", exc_info=True)
            return

        buffer = widget.get_buffer()
        tag = buffer.get_tag_table().lookup("md-search-current")
        if tag is None:
            rgba = _rgba(CURRENT_BG_DARK if self._is_dark else CURRENT_BG_LIGHT)
            tag = buffer.create_tag("md-search-current", background_rgba=rgba)
        buffer.apply_tag(
            tag,
            buffer.get_iter_at_offset(match["start"]),
            buffer.get_iter_at_offset(match["end"]),
        )

    def _scroll_to(self, widget) -> None:
        scrolled = self.viewer.preview_scroll
        column = self.viewer.outer_box
        try:
            ok, rect = widget.compute_bounds(column)
        except Exception:
            logger.debug("Could not measure the matched block", exc_info=True)
            return
        if not ok:
            return
        adjustment = scrolled.get_vadjustment()
        if adjustment is None:
            return
        target = max(0.0, rect.origin.y - 80)
        upper = max(0.0, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(min(target, upper))


def _rgba(hex_value: int):
    from gi.repository import Gdk

    red = ((hex_value >> 16) & 0xFF) / 255.0
    green = ((hex_value >> 8) & 0xFF) / 255.0
    blue = (hex_value & 0xFF) / 255.0
    rgba = Gdk.RGBA()
    rgba.red, rgba.green, rgba.blue, rgba.alpha = red, green, blue, 1.0
    return rgba
