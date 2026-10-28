import os
import re
import json
import logging
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango, PangoCairo, Adw

try:
    import pygments
    from pygments import lexers
    from pygments.token import Token
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from utils.formatters import format_size
from utils.i18n import _, ngettext
from utils.quote import format_line_reference
from widgets.quote_bar import QuoteBar

_CSS_INSTALLED = False
_CSS_PROVIDER = None
_DARK_HANDLER_CONNECTED = False

logger = logging.getLogger(__name__)

# One accent, one dedicated code surface and its text colour (light / dark).
ACCENT_LIGHT = "#3867D6"
ACCENT_DARK = "#8AB4FF"
CODE_SURFACE_LIGHT = "#F6F6F7"
CODE_SURFACE_DARK = "#1C1C1E"
CODE_TEXT_LIGHT = "#1F2328"
CODE_TEXT_DARK = "#E6E6E6"

# Documented untrusted-input limits (SECURITY.md). Content is read as bytes
# and capped before decoding; syntax highlighting only ever sees a prefix.
TEXT_READ_LIMIT = 5 * 1024 * 1024
TEXT_TRUNCATED_PREVIEW_BYTES = 512 * 1024
TEXT_HIGHLIGHT_LIMIT = 1024 * 1024
TEXT_ASYNC_READ_THRESHOLD = 1024 * 1024
_READ_CHUNK_SIZE = 64 * 1024

CODE_VIEWER_CSS = """
@define-color sp_accent %(accent)s;
@define-color sp_code_surface %(code_surface)s;
@define-color sp_code_text %(code_text)s;

.code-toolbar {
    background-color: @headerbar_bg_color;
    border-bottom: 1px solid @borders;
    padding: 8px 16px;
}
.code-lang-badge {
    background-color: alpha(@sp_accent, 0.14);
    color: @sp_accent;
    border: 1px solid alpha(@sp_accent, 0.32);
    border-radius: 6px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.6px;
}
.code-meta-label {
    color: alpha(@window_fg_color, 0.65);
    font-size: 12px;
}
.code-view-surface {
    background-color: @sp_code_surface;
    color: @sp_code_text;
    font-family: "Adwaita Mono", "JetBrains Mono", "Source Code Pro", monospace;
    font-size: 13px;
}
.code-view-surface text {
    background-color: @sp_code_surface;
    color: @sp_code_text;
}
.code-view-surface selection {
    background-color: alpha(@sp_accent, 0.34);
    color: @sp_code_text;
}
.code-gutter {
    background-color: @sp_code_surface;
    border-right: 1px solid @borders;
}
.code-btn-small {
    padding: 3px 10px;
    min-height: 26px;
    font-size: 12px;
    border-radius: 6px;
    transition: background-color 100ms ease-out, color 100ms ease-out;
}
.code-btn-small:active {
    transform: scale(0.98);
}
.code-btn-small:focus {
    outline-color: @sp_accent;
}
.code-search-bar {
    background-color: @view_bg_color;
    border: 1px solid @borders;
    border-radius: 10px;
    padding: 6px 10px;
}
.search-count-label {
    font-size: 12px;
    color: alpha(@window_fg_color, 0.70);
    margin: 0 4px;
}
.search-entry-flat {
    min-width: 250px;
    border-radius: 6px;
}
"""


def is_dark_theme() -> bool:
    """Return whether the system currently prefers a dark colour scheme."""
    try:
        manager = Adw.StyleManager.get_default()
        return bool(manager and manager.get_dark())
    except Exception:
        return False


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    """Convert ``#RRGGBB`` to floats in the 0..1 range used by Cairo."""
    raw = value.lstrip("#")
    return tuple(int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _code_palette(dark: bool) -> dict:
    return {
        "accent": ACCENT_DARK if dark else ACCENT_LIGHT,
        "code_surface": CODE_SURFACE_DARK if dark else CODE_SURFACE_LIGHT,
        "code_text": CODE_TEXT_DARK if dark else CODE_TEXT_LIGHT,
        "muted": "#8B949E" if dark else "#6B7280",
        "green": "#7FB89A" if dark else "#3F7A5A",
        "red": "#D08989" if dark else "#A34A4A",
    }


def _render_code_viewer_css(dark: bool) -> str:
    palette = _code_palette(dark)
    return CODE_VIEWER_CSS % {
        "accent": palette["accent"],
        "code_surface": palette["code_surface"],
        "code_text": palette["code_text"],
    }


def _reload_code_viewer_css(*_args) -> None:
    if _CSS_PROVIDER is not None:
        _CSS_PROVIDER.load_from_data(
            _render_code_viewer_css(is_dark_theme()).encode("utf-8")
        )


def ensure_code_viewer_css():
    global _CSS_INSTALLED, _CSS_PROVIDER, _DARK_HANDLER_CONNECTED
    if _CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    if _CSS_PROVIDER is None:
        _CSS_PROVIDER = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            display, _CSS_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    _CSS_PROVIDER.load_from_data(
        _render_code_viewer_css(is_dark_theme()).encode("utf-8")
    )
    if not _DARK_HANDLER_CONNECTED:
        manager = Adw.StyleManager.get_default()
        if manager is not None:
            manager.connect("notify::dark", _reload_code_viewer_css)
            _DARK_HANDLER_CONNECTED = True
    _CSS_INSTALLED = True


def syntax_tag_colors(dark: bool) -> dict:
    """Return a desaturated syntax palette: one blue, grey, diff-only colour."""
    palette = _code_palette(dark)
    accent = palette["accent"]
    text = palette["code_text"]
    muted = palette["muted"]
    green = palette["green"]
    red = palette["red"]
    return {
        Token.Keyword: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Keyword.Constant: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Keyword.Declaration: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Keyword.Namespace: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Keyword.Type: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Name.Builtin: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Name.Builtin.Pseudo: (text, Pango.Weight.NORMAL, Pango.Style.ITALIC),
        Token.Name.Function: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name.Function.Magic: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name.Class: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name.Decorator: (muted, Pango.Weight.BOLD, Pango.Style.ITALIC),
        Token.Name.Tag: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name.Attribute: (text, Pango.Weight.NORMAL, Pango.Style.ITALIC),
        Token.Name.Constant: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Name.Exception: (text, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Name.Variable: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Literal.String: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Literal.String.Doc: (muted, Pango.Weight.NORMAL, Pango.Style.ITALIC),
        Token.Literal.String.Escape: (muted, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Literal.String.Interpol: (accent, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Literal.Number: (text, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Operator: (muted, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Operator.Word: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Punctuation: (muted, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Comment: (muted, Pango.Weight.NORMAL, Pango.Style.ITALIC),
        Token.Generic.Heading: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Generic.Subheading: (accent, Pango.Weight.BOLD, Pango.Style.NORMAL),
        Token.Generic.Inserted: (green, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Generic.Deleted: (red, Pango.Weight.NORMAL, Pango.Style.NORMAL),
        Token.Generic.Emph: (text, Pango.Weight.NORMAL, Pango.Style.ITALIC),
        Token.Generic.Strong: (text, Pango.Weight.BOLD, Pango.Style.NORMAL),
    }


def detect_lexer_and_label(file_path: str = None, content: str = "", lang_hint: str = None):
    """Detect Pygments lexer and a human-readable language badge name."""
    if not HAS_PYGMENTS:
        ext = os.path.splitext(file_path or "")[1].lstrip(".").upper()
        return None, (lang_hint or ext or "").upper() or _("TEXT")

    lexer = None
    if lang_hint:
        alias = lang_hint.strip().lower()
        alias_map = {
            "ts": "typescript",
            "tsx": "tsx",
            "js": "javascript",
            "jsx": "jsx",
            "py": "python",
            "sh": "bash",
            "shell": "bash",
            "zsh": "bash",
            "yml": "yaml",
            "md": "markdown",
            "mmd": "text",
            "mermaid": "text",
        }
        alias = alias_map.get(alias, alias)
        try:
            lexer = lexers.get_lexer_by_name(alias)
        except Exception:
            lexer = None

    if lexer is None and file_path:
        ext = os.path.splitext(file_path)[1].lower()
        ext_alias = {
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "jsx",
            ".vue": "html",
            ".svelte": "html",
            ".mmd": "text",
            ".mermaid": "text",
            ".jsonc": "json",
            ".env": "ini",
            ".conf": "ini",
        }.get(ext)
        if ext_alias:
            try:
                lexer = lexers.get_lexer_by_name(ext_alias)
            except Exception:
                lexer = None

        if lexer is None:
            try:
                lexer = lexers.get_lexer_for_filename(file_path, content[:4096])
            except Exception:
                lexer = None

    if lexer is None:
        try:
            lexer = lexers.get_lexer_by_name("text")
        except Exception:
            return None, _("TEXT")

    name = getattr(lexer, "name", "Text")
    if name.lower() in ("text only", "plaintext", "text"):
        ext = os.path.splitext(file_path or "")[1].lstrip(".").upper()
        label = (lang_hint or ext or "").upper() or _("TEXT")
    else:
        label = name.upper()
    return lexer, label


def highlight_buffer_with_pygments(
    buffer: Gtk.TextBuffer,
    content: str,
    file_path: str = None,
    lang_hint: str = None,
    max_bytes: int = TEXT_HIGHLIGHT_LIMIT,
) -> str:
    """Populate a Gtk.TextBuffer with syntax-highlighted tokens and return language label.

    ``max_bytes`` bounds the text handed to Pygments. Content above the cap is
    rendered as plain text so a hostile file cannot stall the main thread.
    """
    lexer, label = detect_lexer_and_label(file_path=file_path, content=content, lang_hint=lang_hint)

    if not HAS_PYGMENTS or lexer is None or len(content.encode("utf-8", errors="replace")) > max_bytes:
        buffer.set_text(content)
        return label

    tag_table = buffer.get_tag_table()
    palette = syntax_tag_colors(is_dark_theme())
    for tok_type, (color, weight, style) in palette.items():
        tag_name = str(tok_type)
        tag = tag_table.lookup(tag_name)
        if tag is None:
            tag = Gtk.TextTag.new(tag_name)
            tag_table.add(tag)
        tag.set_property("foreground", color)
        tag.set_property("weight", weight)
        tag.set_property("style", style)

    buffer.set_text("")
    tokens = pygments.lex(content, lexer)

    for tok_type, val in tokens:
        if not val:
            continue
        iter_end = buffer.get_end_iter()
        matched_tag = None
        cur_type = tok_type
        while cur_type:
            if cur_type in palette:
                matched_tag = str(cur_type)
                break
            cur_type = cur_type.parent

        if matched_tag:
            buffer.insert_with_tags_by_name(iter_end, val, matched_tag)
        else:
            buffer.insert(iter_end, val)

    return label


def split_at_byte_limit(content: str, max_bytes: int) -> tuple[str, str]:
    """Split ``content`` so the prefix holds at most ``max_bytes`` of UTF-8.

    The suffix starts at the first character that did not fit, so no content
    is lost when the cut lands inside a multi-byte character.
    """
    encoded = content.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return content, ""
    prefix = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return prefix, content[len(prefix):]


def _read_text_file(file_path: str, size: int, cancellable=None):
    """Read at most the documented byte cap and decode it.

    Files above ``TEXT_READ_LIMIT`` yield a short prefix plus a translated
    truncation note. ``cancellable`` is checked between chunks so teardown
    does not have to wait for a large read. Returns ``None`` when cancelled.
    """
    truncated = size > TEXT_READ_LIMIT
    read_limit = TEXT_TRUNCATED_PREVIEW_BYTES if truncated else TEXT_READ_LIMIT
    chunks = []
    remaining = read_limit
    with open(file_path, "rb") as handle:
        while remaining > 0:
            if cancellable is not None and cancellable.is_cancelled():
                return None
            chunk = handle.read(min(_READ_CHUNK_SIZE, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        # ``getsize`` can be stale; detect a file that grew past the cap.
        if not truncated and handle.read(1):
            truncated = True

    content = b"".join(chunks).decode("utf-8", errors="replace")
    if truncated:
        content += _("\n\n... [Truncated preview: file is larger than 5 MB] ...")
    return content


class TextViewer(Gtk.Box):
    def __init__(self, file_path: str, raw_content: str = None, show_toolbar: bool = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        ensure_code_viewer_css()

        self.file_path = file_path
        self.raw_content = raw_content
        self.displayed_content = ""
        self.is_json_pretty = True
        self.line_count = 1
        self.search_matches = []
        self.current_match_idx = -1

        self._size_bytes = 0
        self._word_count = 0
        self._copy_timeout_id = None
        self._search_open = False
        self.search_state_callback = None
        self._status_callback = None
        self._ready_callback = None

        # Line-range quote state. Both are 0-based line indices; ``None`` means
        # no range is active. The gutter gesture sets them, the buffer
        # selection mirrors them, and the floating card copies them.
        self._quote_anchor = None
        self._quote_cursor = None
        self._quote_drag_start_y = 0.0

        # Every load gets a generation; results from an older generation are
        # discarded. Reads above TEXT_ASYNC_READ_THRESHOLD run on a worker.
        self._load_generation = 0
        self._load_cancellable = None
        self._load_thread = None

        # Controls live in the window header now. The widgets are kept as
        # parentless controls so the window can pack them in its header; no
        # per-viewer toolbar row is appended to this widget.
        self.toolbar = None
        self.lbl_lang = Gtk.Label(label=_("CODE"))
        self.lbl_lang.add_css_class("code-lang-badge")
        self.lbl_stats = Gtk.Label(label="")
        self.lbl_stats.add_css_class("code-meta-label")
        self.lbl_stats.set_halign(Gtk.Align.START)
        self.lbl_stats.set_hexpand(True)

        if show_toolbar:
            # Optional JSON Pretty-Print toggle button
            self.btn_json_pretty = Gtk.ToggleButton(label="{}")
            self.btn_json_pretty.add_css_class("code-btn-small")
            self.btn_json_pretty.set_tooltip_text(_("Pretty-print JSON"))
            self.btn_json_pretty.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Pretty-print JSON")]
            )
            self.btn_json_pretty.set_active(True)
            self.btn_json_pretty.set_visible(False)
            self.btn_json_pretty.connect("toggled", self.on_json_pretty_toggled)

            # Word Wrap toggle button
            self.btn_wrap = Gtk.ToggleButton()
            self.btn_wrap.set_icon_name("format-justify-fill-symbolic")
            self.btn_wrap.add_css_class("code-btn-small")
            self.btn_wrap.set_tooltip_text(_("Toggle word wrap"))
            self.btn_wrap.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Toggle word wrap")]
            )
            self.btn_wrap.set_active(True)
            self.btn_wrap.connect("toggled", self.on_wrap_toggled)

            # Find in Code button
            self.btn_find = Gtk.Button.new_from_icon_name("edit-find-symbolic")
            self.btn_find.add_css_class("code-btn-small")
            self.btn_find.set_tooltip_text(_("Find in code (Ctrl+F)"))
            self.btn_find.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Find in code")]
            )
            self.btn_find.connect("clicked", lambda *_: self.toggle_search())

            # Copy Code button
            self.btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            self.btn_copy.add_css_class("code-btn-small")
            self.btn_copy.set_tooltip_text(_("Copy code"))
            self.btn_copy.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Copy code")]
            )
            self.btn_copy.connect("clicked", self.on_copy_clicked)
        else:
            self.btn_json_pretty = None
            self.btn_wrap = None
            self.btn_find = None
            self.btn_copy = None

        # In-file search (Ctrl+F). The window hosts this box in a
        # non-grabbing overlay; it is intentionally not appended here.
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_box.add_css_class("code-search-bar")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.add_css_class("search-entry-flat")
        self.search_entry.set_placeholder_text(_("Find in code... (Enter to find next)"))
        self.search_entry.set_hexpand(False)
        self.search_box.append(self.search_entry)

        self.lbl_search_count = Gtk.Label(label="")
        self.lbl_search_count.add_css_class("search-count-label")
        self.search_box.append(self.lbl_search_count)

        self.btn_search_prev = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.btn_search_prev.add_css_class("code-btn-small")
        self.btn_search_prev.set_tooltip_text(_("Previous match (Shift+Enter)"))
        self.btn_search_prev.connect("clicked", lambda *_: self.on_find_prev())
        self.search_box.append(self.btn_search_prev)

        self.btn_search_next = Gtk.Button.new_from_icon_name("go-down-symbolic")
        self.btn_search_next.add_css_class("code-btn-small")
        self.btn_search_next.set_tooltip_text(_("Next match (Enter)"))
        self.btn_search_next.connect("clicked", lambda *_: self.on_find_next())
        self.search_box.append(self.btn_search_next)

        self.btn_search_case = Gtk.ToggleButton(label="Aa")
        self.btn_search_case.add_css_class("code-btn-small")
        self.btn_search_case.set_tooltip_text(_("Match Case"))
        self.btn_search_case.connect("toggled", lambda *_: self.on_search_query_changed())
        self.search_box.append(self.btn_search_case)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.search_box.append(spacer)

        self.btn_search_close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.btn_search_close.add_css_class("code-btn-small")
        self.btn_search_close.set_tooltip_text(_("Close Search (Esc)"))
        self.btn_search_close.connect("clicked", lambda *_: self.close_search())
        self.search_box.append(self.btn_search_close)

        # Connect search signals
        self.search_entry.connect("search-changed", self.on_search_query_changed)
        self.search_entry.connect("activate", lambda *_: self.on_find_next())
        self.search_entry.connect("next-match", lambda *_: self.on_find_next())
        self.search_entry.connect("previous-match", lambda *_: self.on_find_prev())
        self.search_entry.connect("stop-search", lambda *_: self.close_search())

        # Key controller for Shift+Enter & Escape inside search entry
        search_key_ctrl = Gtk.EventControllerKey.new()
        search_key_ctrl.connect("key-pressed", self._on_search_entry_key)
        self.search_entry.add_controller(search_key_ctrl)

        # Main Editor Container: Gutter + Scrolled TextView
        self.editor_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.editor_row.set_hexpand(True)
        self.editor_row.set_vexpand(True)

        # The line-range card floats over the editor and never reflows it.
        self.content_overlay = Gtk.Overlay()
        self.content_overlay.set_hexpand(True)
        self.content_overlay.set_vexpand(True)
        self.content_overlay.set_child(self.editor_row)
        self.append(self.content_overlay)

        # Line numbers gutter
        self.gutter = Gtk.DrawingArea()
        self.gutter.add_css_class("code-gutter")
        self.gutter.set_content_width(52)
        self.gutter.set_vexpand(True)
        self.gutter.set_draw_func(self.draw_line_numbers)
        self.gutter.set_tooltip_text(
            _("Drag line numbers to copy a range")
        )
        self.editor_row.append(self.gutter)

        gutter_drag = Gtk.GestureDrag.new()
        gutter_drag.set_button(Gdk.BUTTON_PRIMARY)
        gutter_drag.connect("drag-begin", self._on_gutter_drag_begin)
        gutter_drag.connect("drag-update", self._on_gutter_drag_update)
        self.gutter.add_controller(gutter_drag)

        # Scrolled Code View
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.editor_row.append(self.scrolled)

        self.text_view = Gtk.TextView()
        self.text_view.add_css_class("code-view-surface")
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(16)
        self.text_view.set_right_margin(20)
        self.text_view.set_top_margin(14)
        self.text_view.set_bottom_margin(16)
        self.text_view.set_pixels_above_lines(2)
        self.text_view.set_pixels_below_lines(2)

        self.buffer = self.text_view.get_buffer()
        self.scrolled.set_child(self.text_view)

        self._build_quote_card()
        self._selection_handler_id = self.buffer.connect(
            "notify::has-selection", self._on_buffer_selection_changed
        )

        # Drag on the gutter selects whole lines. Ctrl+Shift+C copies the
        # current line range (or the text selection) as a quote. The window
        # also handles the shortcut in its capture phase.
        quote_keys = Gtk.EventControllerKey.new()
        quote_keys.connect("key-pressed", self._on_quote_key_pressed)
        self.text_view.add_controller(quote_keys)

        text_click = Gtk.GestureClick.new()
        text_click.connect("pressed", self._on_text_pressed)
        self.text_view.add_controller(text_click)

        # Redraw line numbers on scroll
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.connect("value-changed", lambda *_: self.gutter.queue_draw())
            vadj.connect("changed", lambda *_: self.gutter.queue_draw())

        self.load_text()

    def load_text(self):
        """Start a load, synchronously for small files and on a worker above 1 MB."""
        self._load_generation += 1
        generation = self._load_generation
        self._cancel_pending_load()
        cancellable = Gio.Cancellable()
        self._load_cancellable = cancellable

        try:
            if self.raw_content is not None:
                content = self.raw_content
                size = len(content.encode("utf-8", errors="replace"))
                self._apply_loaded_content(content, size, generation)
                return

            size = os.path.getsize(self.file_path)
            if size > TEXT_ASYNC_READ_THRESHOLD:
                self._load_thread = threading.Thread(
                    target=self._worker_load_file,
                    args=(size, generation, cancellable),
                    daemon=True,
                )
                self._load_thread.start()
                return

            content = _read_text_file(self.file_path, size, cancellable)
            if content is not None:
                self._apply_loaded_content(content, size, generation)
        except Exception as e:
            self._show_load_error(e)

    def _worker_load_file(self, size: int, generation: int, cancellable) -> None:
        try:
            content = _read_text_file(self.file_path, size, cancellable)
        except Exception as e:
            if not cancellable.is_cancelled():
                GLib.idle_add(self._on_load_failed, generation, str(e))
            return
        if content is None or cancellable.is_cancelled():
            return
        GLib.idle_add(self._on_load_ready, generation, content, size)

    def _on_load_ready(self, generation: int, content: str, size: int):
        if generation != self._load_generation or self._load_cancellable is None:
            return False
        if self._load_cancellable.is_cancelled():
            return False
        self._load_thread = None
        self._load_cancellable = None
        self._apply_loaded_content(content, size, generation)
        return False

    def _on_load_failed(self, generation: int, error: str):
        if generation != self._load_generation:
            return False
        self._load_thread = None
        self._load_cancellable = None
        self._show_load_error(error)
        return False

    def _cancel_pending_load(self) -> None:
        if self._load_cancellable is not None:
            self._load_cancellable.cancel()
            self._load_cancellable = None

    def _show_load_error(self, error) -> None:
        self.buffer.set_text(
            _("Could not read text file:\n{error}").format(error=error)
        )

    def _apply_loaded_content(self, content: str, size: int, generation: int) -> None:
        if generation != self._load_generation:
            return
        self.raw_content = content

        ext = os.path.splitext(self.file_path or "")[1].lower()
        if ext in (".json", ".jsonc") and len(content) <= 512 * 1024:
            try:
                parsed = json.loads(content)
                pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
                if self.btn_json_pretty:
                    self.btn_json_pretty.set_visible(True)
                if self.is_json_pretty:
                    content = pretty
            except Exception:
                logger.debug(
                    "Could not pretty-print JSON %s", self.file_path, exc_info=True
                )

        self._render_content(content, size)
        self._notify_status_changed()
        self._notify_ready()

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logging.getLogger(__name__).exception("Text status callback failed")

    def _render_content(self, content: str, size: int):
        # New content invalidates any line range from the previous buffer.
        self._quote_anchor = None
        self._quote_cursor = None
        self._clear_quote_highlight()
        self._update_quote_card()

        self.displayed_content = content
        self.line_count = content.count("\n") + 1
        words = len(re.findall(r"\S+", content))
        self._size_bytes = size
        self._word_count = words

        digits = max(3, len(str(self.line_count)))
        self.gutter.set_content_width(digits * 9 + 24)

        if len(content.encode("utf-8", errors="replace")) > TEXT_HIGHLIGHT_LIMIT:
            # Above the highlight cap, never hand the buffer to Pygments.
            note = _(
                "\n\n... [Syntax highlighting disabled: file is larger than 1 MB; "
                "showing plain text] ..."
            )
            self.buffer.set_text(content + note)
            lang_label = detect_lexer_and_label(
                file_path=self.file_path, content=content
            )[1]
        else:
            lang_label = highlight_buffer_with_pygments(
                self.buffer, content, file_path=self.file_path
            )

        if self.lbl_lang:
            self.lbl_lang.set_text(lang_label)
        if self.lbl_stats:
            lines_text = ngettext("{count} line", "{count} lines", self.line_count).format(
                count=f"{self.line_count:,}"
            )
            words_text = ngettext("{count} word", "{count} words", words).format(
                count=f"{words:,}"
            )
            self.lbl_stats.set_text(
                _("{lines}  •  {words}  •  {size}").format(
                    lines=lines_text, words=words_text, size=format_size(size)
                )
            )

        self.gutter.queue_draw()

    def draw_line_numbers(self, area, cr, width, height):
        dark = is_dark_theme()
        palette = _code_palette(dark)
        cr.set_source_rgb(*hex_to_rgb(palette["code_surface"]))
        cr.rectangle(0, 0, width, height)
        cr.fill()

        quote_lo = quote_hi = None
        quote_rgb = None
        if self._quote_anchor is not None and self._quote_cursor is not None:
            quote_lo = min(self._quote_anchor, self._quote_cursor) + 1
            quote_hi = max(self._quote_anchor, self._quote_cursor) + 1
            quote_rgb = hex_to_rgb(ACCENT_DARK if dark else ACCENT_LIGHT)

        vadj = self.scrolled.get_vadjustment()
        scroll_y = int(vadj.get_value()) if vadj else 0
        top_margin = self.text_view.get_top_margin()

        layout = PangoCairo.create_layout(cr)
        font_desc = Pango.FontDescription.from_string("Monospace 10")
        layout.set_font_description(font_desc)
        cr.set_source_rgba(*hex_to_rgb(palette["muted"]), 0.85)

        y_buf = max(0, scroll_y - top_margin)
        end_buf_y = scroll_y + height

        res = self.text_view.get_line_at_y(y_buf)
        it = res[0] if isinstance(res, tuple) else res

        visited_lines = set()
        max_iters = 400
        count = 0

        while count < max_iters:
            count += 1
            line_num = it.get_line() + 1
            yrange = self.text_view.get_line_yrange(it)
            line_y = yrange[0] if isinstance(yrange, tuple) else 0
            line_h = yrange[1] if isinstance(yrange, tuple) else 18

            win_y = line_y + top_margin - scroll_y
            if win_y > height:
                break

            if line_num not in visited_lines and (win_y + line_h) >= 0:
                visited_lines.add(line_num)
                if quote_rgb is not None and quote_lo <= line_num <= quote_hi:
                    cr.set_source_rgba(*quote_rgb, 0.16)
                    cr.rectangle(0, win_y, width, line_h)
                    cr.fill()
                    cr.set_source_rgba(*quote_rgb, 0.85)
                    cr.rectangle(0, win_y, 2, line_h)
                    cr.fill()
                    cr.set_source_rgba(*hex_to_rgb(palette["muted"]), 0.85)
                text_str = str(line_num)
                layout.set_text(text_str, -1)
                ink_rect, logical_rect = layout.get_pixel_extents()
                x_pos = max(6, width - logical_rect.width - 10)
                cr.move_to(x_pos, win_y + 2)
                PangoCairo.show_layout(cr, layout)

            if it.is_end():
                break
            if not it.forward_line():
                break
            if line_y > end_buf_y:
                break

    def on_wrap_toggled(self, btn):
        if btn.get_active():
            self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        else:
            self.text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.gutter.queue_draw()

    def on_json_pretty_toggled(self, btn):
        self.is_json_pretty = btn.get_active()
        self.load_text()

    def on_copy_clicked(self, btn):
        display = Gdk.Display.get_default()
        if display and self.displayed_content:
            clipboard = display.get_clipboard()
            clipboard.set(self.displayed_content)
            btn.set_label(_("Copied!"))
            if self._copy_timeout_id is not None:
                GLib.source_remove(self._copy_timeout_id)
            self._copy_timeout_id = GLib.timeout_add(1400, self._reset_copy_label)

    def _reset_copy_label(self):
        self._copy_timeout_id = None
        if self.btn_copy is not None:
            self.btn_copy.set_label(_("Copy"))
        return False

    # ----------------------------------------------------- line-range quotes

    def _build_quote_card(self) -> None:
        """Create the floating card shown while text or whole lines are selected."""
        self.quote_bar = QuoteBar(self.copy_selected_lines)
        self.content_overlay.add_overlay(self.quote_bar)

    def _quote_tag(self):
        """Return the buffer tag used to paint a gutter range, creating it once."""
        tag = self.buffer.get_tag_table().lookup("quote-range")
        if tag is not None:
            return tag

        dark = is_dark_theme()
        red, green, blue = hex_to_rgb(ACCENT_DARK if dark else ACCENT_LIGHT)
        rgba = Gdk.RGBA()
        rgba.red = red
        rgba.green = green
        rgba.blue = blue
        rgba.alpha = 0.18
        tag = self.buffer.create_tag(
            "quote-range", background_rgba=rgba, background_full_height=True
        )
        return tag

    def _apply_quote_highlight(self) -> None:
        tag = self._quote_tag()
        self.buffer.remove_tag(
            tag, self.buffer.get_start_iter(), self.buffer.get_end_iter()
        )
        if self._quote_anchor is None or self._quote_cursor is None:
            return
        first = min(self._quote_anchor, self._quote_cursor)
        last = max(self._quote_anchor, self._quote_cursor)
        self.buffer.apply_tag(
            tag, self._iter_at_line(first), self._iter_at_line(last + 1)
        )

    def _clear_quote_highlight(self) -> None:
        tag = self.buffer.get_tag_table().lookup("quote-range")
        if tag is not None:
            self.buffer.remove_tag(
                tag, self.buffer.get_start_iter(), self.buffer.get_end_iter()
            )

    def _iter_at_line(self, line_index: int):
        line_index = max(0, min(line_index, self.line_count))
        result = self.buffer.get_iter_at_line(line_index)
        return result[-1] if isinstance(result, tuple) else result

    def _line_at_gutter_y(self, y: float) -> int:
        """Map a gutter-local y coordinate to a 0-based buffer line."""
        vadj = self.scrolled.get_vadjustment()
        scroll_y = int(vadj.get_value()) if vadj else 0
        buffer_y = int(y) + scroll_y - self.text_view.get_top_margin()
        result = self.text_view.get_line_at_y(max(0, buffer_y))
        text_iter = result[0] if isinstance(result, tuple) else result
        return text_iter.get_line()

    def _on_gutter_drag_begin(self, gesture, start_x: float, start_y: float) -> None:
        self._quote_drag_start_y = start_y
        try:
            state = gesture.get_current_event_state()
            if isinstance(state, tuple):
                state = state[-1]
            shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        except Exception:
            shift = False

        line = self._line_at_gutter_y(start_y)
        anchor = self._quote_anchor
        if shift and anchor is not None:
            self._set_quote_range(anchor, line)
        else:
            self._set_quote_range(line, line)

    def _on_gutter_drag_update(self, gesture, offset_x: float, offset_y: float) -> None:
        if self._quote_anchor is None:
            return
        line = self._line_at_gutter_y(self._quote_drag_start_y + offset_y)
        self._set_quote_range(self._quote_anchor, line)

    def _set_quote_range(self, anchor: int, cursor: int) -> None:
        max_line = max(0, self.line_count - 1)
        self._quote_anchor = max(0, min(max_line, anchor))
        self._quote_cursor = max(0, min(max_line, cursor))
        if self.buffer.get_has_selection():
            # The gutter range replaces a text selection; two highlights at
            # once would be ambiguous.
            insert = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            self.buffer.place_cursor(insert)
        self._apply_quote_highlight()
        self._update_quote_card()
        self.gutter.queue_draw()

    def _quote_bounds(self, whole_lines: bool = False):
        """Return ``(first_line, last_line, text)`` 0-based, or ``None``.

        A gutter range always covers whole lines. A text selection covers
        exactly what the user dragged, unless ``whole_lines`` is requested for
        a quote payload.
        """
        if self._quote_anchor is not None and self._quote_cursor is not None:
            first = min(self._quote_anchor, self._quote_cursor)
            last = max(self._quote_anchor, self._quote_cursor)
            text = self.buffer.get_text(
                self._iter_at_line(first), self._iter_at_line(last + 1), True
            )
            return first, last, text

        bounds = self.buffer.get_selection_bounds()
        if not bounds:
            return None
        start, end = bounds
        first = start.get_line()
        last = end.get_line()
        # A selection that stops at column 0 does not include the next line.
        if last > first and end.get_line_offset() == 0:
            last -= 1

        if whole_lines:
            start = self._iter_at_line(first)
            end = self._iter_at_line(last + 1)
        return first, last, self.buffer.get_text(start, end, True)

    def has_line_selection(self) -> bool:
        """Return ``True`` only for a gutter-anchored whole-line range."""
        return self._quote_anchor is not None and self._quote_cursor is not None

    def _clear_quote_range(self) -> None:
        self._quote_anchor = None
        self._quote_cursor = None
        self._clear_quote_highlight()
        self._update_quote_card()
        self.gutter.queue_draw()

    def clear_line_selection(self) -> None:
        """Drop the whole-line range; the window calls this on Escape."""
        self._clear_quote_range()

    def _on_text_pressed(self, gesture, n_press: int, x: float, y: float) -> None:
        """A click in the text drops the gutter range and lets selection take over."""
        if self._quote_anchor is not None:
            self._clear_quote_range()

    def _on_buffer_selection_changed(self, *_args) -> None:
        if self._quote_anchor is not None:
            # Selecting text supersedes the gutter range. A focus change that
            # only collapses the selection must not drop the range.
            if not self.buffer.get_selection_bounds():
                return
            self._clear_quote_range()
            return
        self._update_quote_card()
        self.gutter.queue_draw()

    def _update_quote_card(self) -> None:
        bar = getattr(self, "quote_bar", None)
        if bar is None:
            return
        bounds = self._quote_bounds()
        if bounds is None:
            bar.hide_bar()
            return
        bar.set_lines(bounds[0] + 1, bounds[1] + 1)

    def copy_selected_lines(self, reference: bool = True) -> bool:
        """Copy the selected lines, or a path:line reference for them."""
        bounds = self._quote_bounds(whole_lines=reference)
        if bounds is None:
            return False
        _first, _last, text = bounds
        if text.endswith("\n"):
            text = text[:-1]
        if not text:
            return False

        if reference:
            payload = format_line_reference(
                self.file_path, bounds[0] + 1, bounds[1] + 1
            )
        else:
            payload = text

        display = Gdk.Display.get_default()
        if display is None:
            return False
        display.get_clipboard().set(payload)
        bar = getattr(self, "quote_bar", None)
        if bar is not None:
            bar.flash(reference)
        return True

    def _on_quote_key_pressed(self, controller, keyval, keycode, state) -> bool:
        if (
            state & Gdk.ModifierType.CONTROL_MASK
            and state & Gdk.ModifierType.SHIFT_MASK
            and keyval in (Gdk.KEY_C, Gdk.KEY_c)
        ):
            return self.copy_selected_lines(reference=True)
        return False

    # -------------------------------------------------------------
    # Search Engine & In-File Search Bar Methods
    # -------------------------------------------------------------
    def _on_search_entry_key(self, ctrl, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                self.on_find_prev()
            else:
                self.on_find_next()
            return True
        if keyval == Gdk.KEY_Escape:
            self.close_search()
            return True
        return False

    def _ensure_search_tags(self):
        palette = _code_palette(is_dark_theme())
        red, green, blue = hex_to_rgb(palette["accent"])
        match_background = (
            f"rgba({int(red * 255)}, {int(green * 255)}, {int(blue * 255)}, 0.28)"
        )
        tag_table = self.buffer.get_tag_table()

        tag_match = tag_table.lookup("search_match")
        if tag_match is None:
            tag_match = Gtk.TextTag.new("search_match")
            tag_table.add(tag_match)
        tag_match.set_property("background", match_background)
        tag_match.set_property("foreground", palette["code_text"])

        tag_current = tag_table.lookup("search_current")
        if tag_current is None:
            tag_current = Gtk.TextTag.new("search_current")
            tag_table.add(tag_current)
        tag_current.set_property("background", palette["accent"])
        tag_current.set_property("foreground", palette["code_surface"])

    def _clear_search_highlights(self):
        tag_table = self.buffer.get_tag_table()
        if tag_table.lookup("search_match"):
            self.buffer.remove_tag_by_name(
                "search_match", self.buffer.get_start_iter(), self.buffer.get_end_iter()
            )
        if tag_table.lookup("search_current"):
            self.buffer.remove_tag_by_name(
                "search_current", self.buffer.get_start_iter(), self.buffer.get_end_iter()
            )
        self.search_matches = []
        self.current_match_idx = -1
        self.lbl_search_count.set_text("")

    def on_search_query_changed(self, *args):
        query = self.search_entry.get_text()
        self._execute_search(query)

    def _execute_search(self, query: str):
        self._clear_search_highlights()
        if not query:
            return

        self._ensure_search_tags()
        flags = (
            Gtk.TextSearchFlags.NONE
            if self.btn_search_case.get_active()
            else Gtk.TextSearchFlags.CASE_INSENSITIVE
        )

        it = self.buffer.get_start_iter()
        limit = self.buffer.get_end_iter()

        while True:
            res = it.forward_search(query, flags, limit)
            if not res:
                break
            m_start, m_end = res
            self.search_matches.append((m_start.get_offset(), m_end.get_offset()))
            it = m_end
            if it.is_end() or len(self.search_matches) >= 2000:
                break

        if not self.search_matches:
            self.lbl_search_count.set_text(_("No matches"))
            return

        # Highlight all matches
        for s_off, e_off in self.search_matches:
            s_it = self.buffer.get_iter_at_offset(s_off)
            e_it = self.buffer.get_iter_at_offset(e_off)
            self.buffer.apply_tag_by_name("search_match", s_it, e_it)

        self.current_match_idx = 0
        self._highlight_and_scroll_current_match()

    def _highlight_and_scroll_current_match(self):
        if not self.search_matches or self.current_match_idx < 0:
            return

        self.buffer.remove_tag_by_name(
            "search_current", self.buffer.get_start_iter(), self.buffer.get_end_iter()
        )

        s_off, e_off = self.search_matches[self.current_match_idx]
        s_it = self.buffer.get_iter_at_offset(s_off)
        e_it = self.buffer.get_iter_at_offset(e_off)
        self.buffer.apply_tag_by_name("search_current", s_it, e_it)

        # Scroll TextView to center match smoothly
        self.text_view.scroll_to_iter(s_it, 0.1, True, 0.0, 0.4)
        self.lbl_search_count.set_text(
            _("{current} / {total}").format(
                current=self.current_match_idx + 1,
                total=len(self.search_matches),
            )
        )

    def on_find_next(self):
        if not self.search_matches:
            return
        self.current_match_idx = (self.current_match_idx + 1) % len(self.search_matches)
        self._highlight_and_scroll_current_match()

    def on_find_prev(self):
        if not self.search_matches:
            return
        self.current_match_idx = (self.current_match_idx - 1) % len(self.search_matches)
        self._highlight_and_scroll_current_match()

    def toggle_search(self):
        if not self._search_open:
            self._search_open = True
            self.search_entry.grab_focus()
            self.search_entry.select_region(0, -1)
            q = self.search_entry.get_text()
            if q:
                self._execute_search(q)
        else:
            self.search_entry.grab_focus()
            self.search_entry.select_region(0, -1)
        self._notify_search_state()

    def set_search_query(self, query: str, open_bar: bool = False) -> None:
        """Carry a query over from another mode without losing the selection."""
        if open_bar and not self._search_open:
            self._search_open = True
            self._notify_search_state()
        self.search_entry.set_text(query or "")
        if query:
            self._execute_search(query)
        self.search_entry.grab_focus()
        self.search_entry.select_region(0, -1)

    def close_search(self):
        if self._search_open:
            self._search_open = False
            self._clear_search_highlights()
            self.text_view.grab_focus()
            self._notify_search_state()

    def is_search_open(self) -> bool:
        return self._search_open

    def set_search_state_callback(self, callback) -> None:
        """Let the window show or hide the overlay that hosts this search box."""
        self.search_state_callback = callback

    def set_status_callback(self, callback) -> None:
        """Register a callback invoked when the status metadata changes."""
        self._status_callback = callback if callable(callback) else None

    def set_ready_callback(self, callback) -> None:
        """Register a callback invoked after the first content render lands."""
        self._ready_callback = callback if callable(callback) else None

    def _notify_ready(self) -> None:
        callback = self._ready_callback
        if callable(callback):
            try:
                callback()
            except Exception:
                logging.getLogger(__name__).exception("Ready callback failed")

    def _notify_search_state(self) -> None:
        callback = self.search_state_callback
        if callable(callback):
            try:
                callback(self._search_open)
            except Exception:
                logging.getLogger(__name__).exception("Search state callback failed")

    def get_header_controls(self) -> list:
        """Return at most three controls, highest priority first."""
        controls = []
        for control in (
            self.btn_find,
            self.btn_wrap,
            self.btn_json_pretty,
            self.btn_copy,
        ):
            if control is not None and control.get_visible():
                controls.append(control)
            if len(controls) == 3:
                break
        return controls

    def get_status_items(self) -> list[tuple[str, str]]:
        return [
            (_("Size"), format_size(self._size_bytes)),
            (_("Lines"), f"{self.line_count:,}"),
            (_("Encoding"), "UTF-8"),
        ]

    def get_search_widget(self):
        """Return the search container for the window overlay."""
        return self.search_box

    def teardown(self) -> None:
        """Cancel the timer and any in-flight background load."""
        self._load_generation += 1
        self._cancel_pending_load()
        self._load_thread = None
        self._status_callback = None
        if self._copy_timeout_id is not None:
            GLib.source_remove(self._copy_timeout_id)
            self._copy_timeout_id = None
        bar = getattr(self, "quote_bar", None)
        if bar is not None:
            bar.teardown()
        handler_id = getattr(self, "_selection_handler_id", None)
        if handler_id is not None:
            try:
                self.buffer.disconnect(handler_id)
            except Exception:
                logger.debug("Could not disconnect the selection handler", exc_info=True)
            self._selection_handler_id = None

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        # Header + status bar + margins + lines * 21px.
        line_h = 21.0
        overhead = 96
        content_h = int(overhead + self.line_count * line_h)
        min_h = 380
        max_h = min(980, int(screen_h * 0.82))
        target_h = max(min_h, min(max_h, content_h))
        return target_w, target_h
