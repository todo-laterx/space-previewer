import os
import re
import json
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

try:
    import pygments
    from pygments import lexers
    from pygments.token import Token
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from utils.formatters import format_size

_CSS_INSTALLED = False

CODE_VIEWER_CSS = """
.code-toolbar {
    background-color: rgba(24, 24, 37, 0.92);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px 16px;
}
.code-lang-badge {
    background-color: rgba(137, 180, 250, 0.16);
    color: #89b4fa;
    border: 1px solid rgba(137, 180, 250, 0.32);
    border-radius: 6px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.6px;
}
.code-meta-label {
    color: rgba(205, 214, 244, 0.65);
    font-size: 12px;
}
.code-view-surface {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "JetBrains Mono", "Fira Code", "Ubuntu Mono", monospace;
    font-size: 13px;
}
.code-view-surface text {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
.code-gutter {
    background-color: #181825;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}
.code-btn-small {
    padding: 3px 10px;
    min-height: 26px;
    font-size: 12px;
    border-radius: 6px;
}
.code-search-bar {
    background-color: #181825;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding: 6px 14px;
}
.search-count-label {
    font-size: 12px;
    color: rgba(205, 214, 244, 0.70);
    margin: 0 4px;
}
.search-entry-flat {
    min-width: 250px;
    border-radius: 6px;
}
"""


def ensure_code_viewer_css():
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CODE_VIEWER_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_INSTALLED = True


# Rich Catppuccin Mocha / One Dark syntax palette
SYNTAX_TAG_COLORS = {
    Token.Keyword: ("#cba6f7", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Keyword.Constant: ("#fab387", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Keyword.Declaration: ("#cba6f7", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Keyword.Namespace: ("#f38ba8", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Keyword.Type: ("#f9e2af", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name: ("#cdd6f4", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Name.Builtin: ("#f38ba8", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Name.Builtin.Pseudo: ("#f38ba8", Pango.Weight.NORMAL, Pango.Style.ITALIC),
    Token.Name.Function: ("#89b4fa", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name.Function.Magic: ("#94e2d5", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name.Class: ("#f9e2af", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name.Decorator: ("#fab387", Pango.Weight.BOLD, Pango.Style.ITALIC),
    Token.Name.Tag: ("#89b4fa", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name.Attribute: ("#f9e2af", Pango.Weight.NORMAL, Pango.Style.ITALIC),
    Token.Name.Constant: ("#fab387", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Name.Exception: ("#eba0ac", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Name.Variable: ("#cdd6f4", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Literal.String: ("#a6e3a1", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Literal.String.Doc: ("#94e2d5", Pango.Weight.NORMAL, Pango.Style.ITALIC),
    Token.Literal.String.Escape: ("#f2cdcd", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Literal.String.Interpol: ("#fab387", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Literal.Number: ("#fab387", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Operator: ("#89dceb", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Operator.Word: ("#cba6f7", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Punctuation: ("#9399b2", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Comment: ("#6c7086", Pango.Weight.NORMAL, Pango.Style.ITALIC),
    Token.Generic.Heading: ("#89b4fa", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Generic.Subheading: ("#74c7ec", Pango.Weight.BOLD, Pango.Style.NORMAL),
    Token.Generic.Inserted: ("#a6e3a1", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Generic.Deleted: ("#f38ba8", Pango.Weight.NORMAL, Pango.Style.NORMAL),
    Token.Generic.Emph: ("#cdd6f4", Pango.Weight.NORMAL, Pango.Style.ITALIC),
    Token.Generic.Strong: ("#cdd6f4", Pango.Weight.BOLD, Pango.Style.NORMAL),
}


def detect_lexer_and_label(file_path: str = None, content: str = "", lang_hint: str = None):
    """Detect Pygments lexer and a human-readable language badge name."""
    if not HAS_PYGMENTS:
        ext = os.path.splitext(file_path or "")[1].lstrip(".").upper()
        return None, (lang_hint or ext or "TEXT").upper()

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
            return None, "TEXT"

    name = getattr(lexer, "name", "Text")
    if name.lower() in ("text only", "plaintext", "text"):
        ext = os.path.splitext(file_path or "")[1].lstrip(".").upper()
        label = (lang_hint or ext or "TEXT").upper()
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
    for tok_type, (color, weight, style) in SYNTAX_TAG_COLORS.items():
        tag_name = str(tok_type)
        if not tag_table.lookup(tag_name):
            tag = Gtk.TextTag.new(tag_name)
            tag.set_property("foreground", color)
            if weight != Pango.Weight.NORMAL:
                tag.set_property("weight", weight)
            if style != Pango.Style.NORMAL:
                tag.set_property("style", style)
            tag_table.add(tag)

    buffer.set_text("")
    tokens = pygments.lex(content, lexer)

    for tok_type, val in tokens:
        if not val:
            continue
        iter_end = buffer.get_end_iter()
        matched_tag = None
        cur_type = tok_type
        while cur_type:
            if cur_type in SYNTAX_TAG_COLORS:
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

        # Top Code Preview Toolbar
        if show_toolbar:
            self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            self.toolbar.add_css_class("code-toolbar")

            self.lbl_lang = Gtk.Label(label="CODE")
            self.lbl_lang.add_css_class("code-lang-badge")
            self.toolbar.append(self.lbl_lang)

            self.lbl_stats = Gtk.Label(label="")
            self.lbl_stats.add_css_class("code-meta-label")
            self.lbl_stats.set_halign(Gtk.Align.START)
            self.lbl_stats.set_hexpand(True)
            self.toolbar.append(self.lbl_stats)

            # Optional JSON Pretty-Print toggle button
            self.btn_json_pretty = Gtk.ToggleButton(label="Pretty JSON")
            self.btn_json_pretty.add_css_class("code-btn-small")
            self.btn_json_pretty.set_active(True)
            self.btn_json_pretty.set_visible(False)
            self.btn_json_pretty.connect("toggled", self.on_json_pretty_toggled)
            self.toolbar.append(self.btn_json_pretty)

            # Word Wrap toggle button
            self.btn_wrap = Gtk.ToggleButton(label="Wrap")
            self.btn_wrap.add_css_class("code-btn-small")
            self.btn_wrap.set_active(True)
            self.btn_wrap.connect("toggled", self.on_wrap_toggled)
            self.toolbar.append(self.btn_wrap)

            # Find in Code button
            self.btn_find = Gtk.Button(label="Find")
            self.btn_find.add_css_class("code-btn-small")
            self.btn_find.set_tooltip_text("Find in code (Ctrl+F)")
            self.btn_find.connect("clicked", lambda *_: self.toggle_search())
            self.toolbar.append(self.btn_find)

            # Copy Code button
            self.btn_copy = Gtk.Button(label="Copy")
            self.btn_copy.add_css_class("code-btn-small")
            self.btn_copy.connect("clicked", self.on_copy_clicked)
            self.toolbar.append(self.btn_copy)

            self.append(self.toolbar)
        else:
            self.lbl_lang = None
            self.lbl_stats = None
            self.btn_json_pretty = None

        # Integrated In-File Search Bar (Ctrl+F)
        self.search_revealer = Gtk.Revealer()
        self.search_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.search_revealer.set_reveal_child(False)

        self.search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_box.add_css_class("code-search-bar")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.add_css_class("search-entry-flat")
        self.search_entry.set_placeholder_text("Find in code... (Enter to find next)")
        self.search_entry.set_hexpand(False)
        self.search_box.append(self.search_entry)

        self.lbl_search_count = Gtk.Label(label="")
        self.lbl_search_count.add_css_class("search-count-label")
        self.search_box.append(self.lbl_search_count)

        self.btn_search_prev = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.btn_search_prev.add_css_class("code-btn-small")
        self.btn_search_prev.set_tooltip_text("Previous match (Shift+Enter)")
        self.btn_search_prev.connect("clicked", lambda *_: self.on_find_prev())
        self.search_box.append(self.btn_search_prev)

        self.btn_search_next = Gtk.Button.new_from_icon_name("go-down-symbolic")
        self.btn_search_next.add_css_class("code-btn-small")
        self.btn_search_next.set_tooltip_text("Next match (Enter)")
        self.btn_search_next.connect("clicked", lambda *_: self.on_find_next())
        self.search_box.append(self.btn_search_next)

        self.btn_search_case = Gtk.ToggleButton(label="Aa")
        self.btn_search_case.add_css_class("code-btn-small")
        self.btn_search_case.set_tooltip_text("Match Case")
        self.btn_search_case.connect("toggled", lambda *_: self.on_search_query_changed())
        self.search_box.append(self.btn_search_case)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.search_box.append(spacer)

        self.btn_search_close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.btn_search_close.add_css_class("code-btn-small")
        self.btn_search_close.set_tooltip_text("Close Search (Esc)")
        self.btn_search_close.connect("clicked", lambda *_: self.close_search())
        self.search_box.append(self.btn_search_close)

        self.search_revealer.set_child(self.search_box)
        self.append(self.search_revealer)

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
                        content = f.read(1024 * 512) + "\n\n... [Truncated preview: file is larger than 5MB] ..."
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
            self.buffer.set_text(f"Could not read text file:\n{e}")

    def _render_content(self, content: str, size: int):
        self.displayed_content = content
        self.line_count = content.count("\n") + 1
        words = sum(1 for _ in re.finditer(r'\S+', content))

        digits = max(3, len(str(self.line_count)))
        self.gutter.set_content_width(digits * 9 + 24)

        lang_label = highlight_buffer_with_pygments(
            self.buffer, content, file_path=self.file_path
        )

        if self.lbl_lang:
            self.lbl_lang.set_text(lang_label)
        if self.lbl_stats:
            self.lbl_stats.set_text(f"{self.line_count:,} lines  •  {words:,} words  •  {format_size(size)}")

        self.gutter.queue_draw()

    def draw_line_numbers(self, area, cr, width, height):
        # Background fill
        cr.set_source_rgba(0.094, 0.094, 0.145, 1.0)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        vadj = self.scrolled.get_vadjustment()
        scroll_y = int(vadj.get_value()) if vadj else 0
        top_margin = self.text_view.get_top_margin()

        layout = PangoCairo.create_layout(cr)
        font_desc = Pango.FontDescription.from_string("Monospace 10")
        layout.set_font_description(font_desc)
        cr.set_source_rgba(0.45, 0.48, 0.60, 0.85)

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
            btn.set_label("Copied!")
            GLib.timeout_add(1400, lambda: (btn.set_label("Copy"), False)[1])

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
        tag_table = self.buffer.get_tag_table()
        if not tag_table.lookup("search_match"):
            tag_match = Gtk.TextTag.new("search_match")
            tag_match.set_property("background", "#45475a")
            tag_match.set_property("foreground", "#cdd6f4")
            tag_table.add(tag_match)

        if not tag_table.lookup("search_current"):
            tag_current = Gtk.TextTag.new("search_current")
            tag_current.set_property("background", "#fab387")
            tag_current.set_property("foreground", "#11111b")
            tag_table.add(tag_current)

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
            self.lbl_search_count.set_text("0 matches")
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
            f"{self.current_match_idx + 1} / {len(self.search_matches)}"
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
        if not self.search_revealer.get_reveal_child():
            self.search_revealer.set_reveal_child(True)
            self.search_entry.grab_focus()
            self.search_entry.select_region(0, -1)
            q = self.search_entry.get_text()
            if q:
                self._execute_search(q)
        else:
            self.search_entry.grab_focus()
            self.search_entry.select_region(0, -1)

    def close_search(self):
        if self.search_revealer.get_reveal_child():
            self.search_revealer.set_reveal_child(False)
            self._clear_search_highlights()
            self.text_view.grab_focus()

    def is_search_open(self) -> bool:
        return self.search_revealer.get_reveal_child()

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        # Responsive height calculation: header (48) + toolbar (42) + margins (30) + lines * 21px
        line_h = 21.0
        overhead = 120
        content_h = int(overhead + self.line_count * line_h)
        min_h = 380
        max_h = min(980, int(screen_h * 0.82))
        target_h = max(min_h, min(max_h, content_h))
        return target_w, target_h
