import os
import re
import json
import logging
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Adw

try:
    import pygments
    from pygments import lexers
    from pygments.token import Token
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from utils.formatters import format_size
from utils.i18n import _, ngettext

_CSS_INSTALLED = False
_CSS_PROVIDER = None
_DARK_HANDLER_CONNECTED = False

# One accent, one dedicated code surface and its text colour (light / dark).
ACCENT_LIGHT = "#4C8DFF"
ACCENT_DARK = "#6EA8FF"
CODE_SURFACE_LIGHT = "#F6F6F7"
CODE_SURFACE_DARK = "#1C1C1E"
CODE_TEXT_LIGHT = "#1F2328"
CODE_TEXT_DARK = "#E6E6E6"

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
) -> str:
    """Populate a Gtk.TextBuffer with syntax-highlighted tokens and return language label."""
    lexer, label = detect_lexer_and_label(file_path=file_path, content=content, lang_hint=lang_hint)
    lines = content.count("\n") + 1

    if not HAS_PYGMENTS or lexer is None or lines > 3000 or len(content) > 300 * 1024:
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
        self.append(self.editor_row)

        # Line numbers gutter
        self.gutter = Gtk.DrawingArea()
        self.gutter.add_css_class("code-gutter")
        self.gutter.set_content_width(52)
        self.gutter.set_vexpand(True)
        self.gutter.set_draw_func(self.draw_line_numbers)
        self.editor_row.append(self.gutter)

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

        # Redraw line numbers on scroll
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.connect("value-changed", lambda *_: self.gutter.queue_draw())
            vadj.connect("changed", lambda *_: self.gutter.queue_draw())

        self.load_text()

    def load_text(self):
        try:
            if self.raw_content is not None:
                content = self.raw_content
                size = len(content.encode("utf-8", errors="replace"))
            else:
                size = os.path.getsize(self.file_path)
                if size > 5 * 1024 * 1024:
                    with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(1024 * 512) + _(
                            "\n\n... [Truncated preview: file is larger than 5 MB] ..."
                        )
                else:
                    with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
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
                    pass

            self._render_content(content, size)

        except Exception as e:
            self.buffer.set_text(
                _("Could not read text file:\n{error}").format(error=e)
            )

    def _render_content(self, content: str, size: int):
        self.displayed_content = content
        self.line_count = content.count("\n") + 1
        words = len(re.findall(r"\S+", content))
        self._size_bytes = size
        self._word_count = words

        digits = max(3, len(str(self.line_count)))
        self.gutter.set_content_width(digits * 9 + 24)

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
        palette = _code_palette(is_dark_theme())
        cr.set_source_rgb(*hex_to_rgb(palette["code_surface"]))
        cr.rectangle(0, 0, width, height)
        cr.fill()

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
        lines_text = ngettext(
            "{count} line", "{count} lines", self.line_count
        ).format(count=f"{self.line_count:,}")
        return [
            (_("Size"), format_size(self._size_bytes)),
            (_("Lines"), lines_text),
            (_("Encoding"), "UTF-8"),
        ]

    def get_search_widget(self):
        """Return the search container for the window overlay."""
        return self.search_box

    def teardown(self) -> None:
        """Cancel the viewer-owned timer; there is no other async work."""
        if self._copy_timeout_id is not None:
            GLib.source_remove(self._copy_timeout_id)
            self._copy_timeout_id = None

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
