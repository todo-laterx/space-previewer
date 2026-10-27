import os
import re
import io
import json
import zlib
import base64
import hashlib
import threading
import urllib.request
import html
import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango, PangoCairo

try:
    from markdown_it import MarkdownIt
    HAS_MARKDOWN_IT = True
except ImportError:
    HAS_MARKDOWN_IT = False

from utils.formatters import format_size
from .text_viewer import (
    TextViewer,
    ensure_code_viewer_css,
    highlight_buffer_with_pygments,
)

_MD_CSS_INSTALLED = False

MARKDOWN_VIEWER_CSS = """
.md-page-bg {
    background-color: #181825;
}
.md-content-column {
    background-color: #1e1e2e;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    padding: 28px 36px;
}
.md-h1 {
    font-size: 26px;
    font-weight: 800;
    color: #cdd6f4;
}
.md-h2 {
    font-size: 21px;
    font-weight: 700;
    color: #cdd6f4;
}
.md-h3 {
    font-size: 17px;
    font-weight: 700;
    color: #bac2de;
}
.md-h4 {
    font-size: 15px;
    font-weight: 700;
    color: #a6adc8;
}
.md-h5, .md-h6 {
    font-size: 13px;
    font-weight: 700;
    color: #9399b2;
}
.md-heading-rule {
    background-color: rgba(255, 255, 255, 0.10);
    min-height: 1px;
}
.md-paragraph {
    font-size: 14px;
    color: #cdd6f4;
}
.md-blockquote {
    background-color: rgba(49, 50, 68, 0.45);
    border-left: 4px solid #89b4fa;
    border-radius: 0 8px 8px 0;
    padding: 10px 16px;
}
.md-alert-note {
    background-color: rgba(137, 180, 250, 0.10);
    border-left: 4px solid #89b4fa;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-tip {
    background-color: rgba(166, 227, 161, 0.10);
    border-left: 4px solid #a6e3a1;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-important {
    background-color: rgba(203, 166, 247, 0.10);
    border-left: 4px solid #cba6f7;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-warning {
    background-color: rgba(249, 226, 175, 0.10);
    border-left: 4px solid #f9e2af;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-caution {
    background-color: rgba(243, 139, 168, 0.10);
    border-left: 4px solid #f38ba8;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-code-card {
    background-color: #11111b;
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 10px;
}
.md-code-card-header {
    background-color: rgba(24, 24, 37, 0.95);
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px 10px 0 0;
    padding: 6px 14px;
}
.md-code-block-view {
    background-color: #11111b;
    color: #cdd6f4;
    font-family: "JetBrains Mono", "Fira Code", "Ubuntu Mono", monospace;
    font-size: 12.5px;
    border-radius: 0 0 10px 10px;
}
.md-code-block-view text {
    background-color: #11111b;
    color: #cdd6f4;
}
.md-mermaid-card {
    background-color: #181825;
    border: 1px solid rgba(137, 180, 250, 0.25);
    border-radius: 10px;
}
.md-mermaid-header {
    background-color: rgba(30, 30, 46, 0.95);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px 10px 0 0;
    padding: 6px 14px;
}
.md-mermaid-badge {
    background-color: rgba(166, 227, 161, 0.16);
    color: #a6e3a1;
    border: 1px solid rgba(166, 227, 161, 0.35);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 11px;
}
.md-mermaid-canvas {
    background-color: #1e1e2e;
    border-radius: 0 0 10px 10px;
    padding: 16px;
}
.md-table-card {
    background-color: #181825;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
}
.md-table-header-cell {
    background-color: rgba(49, 50, 68, 0.85);
    border-bottom: 1px solid rgba(255, 255, 255, 0.14);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px 14px;
}
.md-table-cell-even {
    background-color: rgba(30, 30, 46, 0.70);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    padding: 7px 14px;
}
.md-table-cell-odd {
    background-color: rgba(24, 24, 37, 0.70);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    padding: 7px 14px;
}
.md-hr {
    background-color: rgba(255, 255, 255, 0.12);
    min-height: 2px;
    margin-top: 8px;
    margin-bottom: 8px;
}
"""

MERMAID_KEYWORDS = (
    "flowchart ",
    "flowchart\n",
    "graph ",
    "graph\n",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "gantt",
    "pie",
    "mindmap",
    "journey",
    "gitGraph",
    "timeline",
    "quadrantChart",
    "xychart-beta",
    "C4Context",
)


def ensure_markdown_css():
    global _MD_CSS_INSTALLED
    ensure_code_viewer_css()
    if _MD_CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(MARKDOWN_VIEWER_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _MD_CSS_INSTALLED = True


def is_mermaid_content(content: str) -> bool:
    """Detect whether raw text is a standalone Mermaid diagram."""
    stripped = content.lstrip()
    # Skip frontmatter or %%{init:...}%% directives
    while stripped.startswith("%%"):
        newline_idx = stripped.find("\n")
        if newline_idx == -1:
            break
        stripped = stripped[newline_idx + 1:].lstrip()
    return any(stripped.startswith(kw) for kw in MERMAID_KEYWORDS)


def detect_mermaid_diagram_type(code: str) -> str:
    stripped = code.lstrip()
    while stripped.startswith("%%"):
        nl = stripped.find("\n")
        if nl == -1:
            break
        stripped = stripped[nl + 1:].lstrip()
    first_word = stripped.split()[0] if stripped.split() else "Diagram"
    mapping = {
        "flowchart": "Flowchart",
        "graph": "Flowchart Graph",
        "sequenceDiagram": "Sequence Diagram",
        "classDiagram": "Class Diagram",
        "stateDiagram": "State Diagram",
        "stateDiagram-v2": "State Diagram",
        "erDiagram": "ER Diagram",
        "gantt": "Gantt Chart",
        "pie": "Pie Chart",
        "mindmap": "Mindmap",
        "journey": "User Journey",
        "gitGraph": "Git Graph",
        "timeline": "Timeline",
        "xychart-beta": "XY Chart",
    }
    return mapping.get(first_word, "Mermaid Diagram")


def render_mermaid_offline_cairo(code: str) -> bytes:
    """Offline fallback diagram renderer using Cairo + Pango so diagrams still preview offline."""
    nodes = {}
    edges = []

    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%%") or line.startswith("flowchart") or line.startswith("graph"):
            continue
        # Match A[Label] --> B[Label] or A --> B
        m = re.match(
            r'^([A-Za-z0-9_]+)(?:\[([^\]]+)\]|"([^"]+)"|\(([^\)]+)\)|\{([^\}]+)\})?\s*'
            r'(-+>|==+>|-\.+->|--\s*[^-]+\s*-->)\s*(?:\|([^|]+)\|)?\s*'
            r'([A-Za-z0-9_]+)(?:\[([^\]]+)\]|"([^"]+)"|\(([^\)]+)\)|\{([^\}]+)\})?',
            line,
        )
        if m:
            src_id = m.group(1)
            src_lbl = m.group(2) or m.group(3) or m.group(4) or m.group(5) or nodes.get(src_id, src_id)
            edge_lbl = m.group(7) or ""
            dst_id = m.group(8)
            dst_lbl = m.group(9) or m.group(10) or m.group(11) or m.group(12) or nodes.get(dst_id, dst_id)
            nodes[src_id] = src_lbl
            nodes[dst_id] = dst_lbl
            edges.append((src_id, dst_id, edge_lbl.strip()))

    if not nodes:
        # Generic visual card for non-flowchart diagram when offline
        lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("%%")][:12]
        width = 680
        height = max(160, 60 + len(lines) * 28)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        cr.set_source_rgb(0.118, 0.118, 0.180)
        cr.paint()
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 11"))
        cr.set_source_rgb(0.537, 0.706, 0.980)
        for idx, l in enumerate(lines):
            layout.set_text(l, -1)
            cr.move_to(24, 24 + idx * 26)
            PangoCairo.show_layout(cr, layout)
        buf = io.BytesIO()
        surface.write_to_png(buf)
        return buf.getvalue()

    node_list = list(nodes.items())
    cols = min(3, max(1, len(node_list)))
    rows = (len(node_list) + cols - 1) // cols
    box_w, box_h = 200, 54
    gap_x, gap_y = 70, 56
    pad_x, pad_y = 40, 36

    width = pad_x * 2 + cols * box_w + max(0, cols - 1) * gap_x
    height = pad_y * 2 + rows * box_h + max(0, rows - 1) * gap_y

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(0.118, 0.118, 0.180)
    cr.paint()

    positions = {}
    for idx, (nid, _) in enumerate(node_list):
        r = idx // cols
        c = idx % cols
        x = pad_x + c * (box_w + gap_x)
        y = pad_y + r * (box_h + gap_y)
        positions[nid] = (x, y)

    # Draw edges
    cr.set_line_width(2.0)
    for src_id, dst_id, elbl in edges:
        if src_id in positions and dst_id in positions:
            x1, y1 = positions[src_id]
            x2, y2 = positions[dst_id]
            sx, sy = x1 + box_w / 2, y1 + box_h / 2
            dx, dy = x2 + box_w / 2, y2 + box_h / 2
            cr.set_source_rgba(0.537, 0.706, 0.980, 0.75)
            cr.move_to(sx, sy)
            cr.line_to(dx, dy)
            cr.stroke()

    # Draw nodes
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 10.5"))
    for nid, label in node_list:
        x, y = positions[nid]
        cr.set_source_rgb(0.192, 0.196, 0.267)
        cr.rectangle(x, y, box_w, box_h)
        cr.fill_preserve()
        cr.set_source_rgb(0.537, 0.706, 0.980)
        cr.set_line_width(1.8)
        cr.stroke()

        layout.set_text(label[:26], -1)
        _, log = layout.get_pixel_extents()
        tx = x + max(8, (box_w - log.width) / 2)
        ty = y + max(6, (box_h - log.height) / 2)
        cr.set_source_rgb(0.804, 0.839, 0.957)
        cr.move_to(tx, ty)
        PangoCairo.show_layout(cr, layout)

    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def fetch_or_render_mermaid_png(code: str) -> bytes:
    """Render Mermaid diagram to PNG bytes instantly via cache or high-speed Cairo renderer."""
    cleaned = code.strip()
    cache_dir = os.path.expanduser("~/.cache/space-previewer/mermaid")
    os.makedirs(cache_dir, exist_ok=True)
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:24]
    cache_path = os.path.join(cache_dir, f"{digest}.png")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
        with open(cache_path, "rb") as f:
            return f.read()

    # 1. Fast local rendering via Cairo (instant ~12ms, zero network lag)
    try:
        data = render_mermaid_offline_cairo(cleaned)
        if data and data.startswith(b"\x89PNG"):
            with open(cache_path, "wb") as f:
                f.write(data)
            return data
    except Exception:
        pass

    # 2. Short-timeout network attempt (max 1.5s, never block)
    try:
        state = {
            "code": cleaned,
            "mermaid": json.dumps({"theme": "dark"}),
        }
        compressed = zlib.compress(json.dumps(state).encode("utf-8"), 9)
        pako = "pako:" + base64.urlsafe_b64encode(compressed).decode("ascii")
        url = f"https://mermaid.ink/img/{pako}?type=png&bgColor=!1e1e2e"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            net_data = resp.read()
            if net_data and net_data.startswith(b"\x89PNG"):
                with open(cache_path, "wb") as f:
                    f.write(net_data)
                return net_data
    except Exception:
        pass

    return render_mermaid_offline_cairo(cleaned)


class MermaidDiagramCard(Gtk.Box):
    """Interactive card widget that renders a Mermaid diagram with Ctrl+Zoom, Drag-to-pan, and code toggle."""

    def __init__(self, code: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("md-mermaid-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        self.code = code.strip()
        self.pixbuf_orig = None
        self.zoom = 1.0
        self.start_hadj = 0.0
        self.start_vadj = 0.0

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("md-mermaid-header")

        badge = Gtk.Label(label="MERMAID")
        badge.add_css_class("md-mermaid-badge")
        header.append(badge)

        dtype = Gtk.Label(label=detect_mermaid_diagram_type(self.code))
        dtype.add_css_class("code-meta-label")
        dtype.set_halign(Gtk.Align.START)
        dtype.set_hexpand(True)
        header.append(dtype)

        # Zoom controls
        btn_zoom_out = Gtk.Button(label="−")
        btn_zoom_out.add_css_class("code-btn-small")
        btn_zoom_out.connect("clicked", lambda *_: self.adjust_zoom(1 / 1.2))
        header.append(btn_zoom_out)

        self.btn_zoom_reset = Gtk.Button(label="100%")
        self.btn_zoom_reset.add_css_class("code-btn-small")
        self.btn_zoom_reset.connect("clicked", lambda *_: self.set_zoom(1.0))
        header.append(self.btn_zoom_reset)

        btn_zoom_in = Gtk.Button(label="+")
        btn_zoom_in.add_css_class("code-btn-small")
        btn_zoom_in.connect("clicked", lambda *_: self.adjust_zoom(1.2))
        header.append(btn_zoom_in)

        # Toggle diagram vs source code
        self.btn_source = Gtk.ToggleButton(label="Source")
        self.btn_source.add_css_class("code-btn-small")
        self.btn_source.connect("toggled", self.on_toggle_source)
        header.append(self.btn_source)

        btn_copy = Gtk.Button(label="Copy")
        btn_copy.add_css_class("code-btn-small")
        btn_copy.connect("clicked", self.on_copy)
        header.append(btn_copy)

        self.append(header)

        # Stack for visual diagram vs source code
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.append(self.stack)

        # Diagram canvas box
        self.canvas_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.canvas_box.add_css_class("md-mermaid-canvas")
        self.canvas_box.set_halign(Gtk.Align.FILL)

        self.spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.spinner_box.set_halign(Gtk.Align.CENTER)
        self.spinner_box.set_margin_top(18)
        self.spinner_box.set_margin_bottom(18)
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.spinner_box.append(self.spinner)
        lbl_loading = Gtk.Label(label="Rendering Mermaid diagram...")
        lbl_loading.add_css_class("code-meta-label")
        self.spinner_box.append(lbl_loading)
        self.canvas_box.append(self.spinner_box)

        # Scrolled window supporting smooth 2D scroll & panning
        self.pic_scroll = Gtk.ScrolledWindow()
        self.pic_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pic_scroll.set_propagate_natural_height(True)
        self.pic_scroll.set_max_content_height(580)
        self.pic_scroll.set_visible(False)

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_halign(Gtk.Align.CENTER)
        self.picture.set_valign(Gtk.Align.CENTER)
        self.pic_scroll.set_child(self.picture)
        self.canvas_box.append(self.pic_scroll)

        # 1. Ctrl + Mouse Scroll for Zoom
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self.on_ctrl_scroll_zoom)
        self.canvas_box.add_controller(scroll_controller)

        # 2. Drag Gesture for Drag-to-Pan (Kéo thả di chuyển sơ đồ)
        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.connect("drag-begin", self.on_drag_begin)
        drag_gesture.connect("drag-update", self.on_drag_update)
        drag_gesture.connect("drag-end", self.on_drag_end)
        self.canvas_box.add_controller(drag_gesture)

        self.stack.add_named(self.canvas_box, "diagram")

        # Source view
        src_tv = Gtk.TextView()
        src_tv.add_css_class("md-code-block-view")
        src_tv.set_editable(False)
        src_tv.set_cursor_visible(False)
        src_tv.set_monospace(True)
        src_tv.set_left_margin(14)
        src_tv.set_right_margin(14)
        src_tv.set_top_margin(12)
        src_tv.set_bottom_margin(12)
        highlight_buffer_with_pygments(src_tv.get_buffer(), self.code, lang_hint="mermaid")
        self.stack.add_named(src_tv, "source")

        self.stack.set_visible_child_name("diagram")

        # Render asynchronously in background thread
        threading.Thread(target=self._worker_render, daemon=True).start()

    def on_ctrl_scroll_zoom(self, controller, dx, dy):
        """Handle Ctrl + Scroll wheel to zoom diagram in/out smoothly."""
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            if dy < 0:
                self.adjust_zoom(1.15)
            else:
                self.adjust_zoom(1 / 1.15)
            return True  # Consume event, preventing outer document scroll
        return False

    def on_drag_begin(self, gesture, start_x, start_y):
        """Initiate drag-to-pan."""
        hadj = self.pic_scroll.get_hadjustment()
        vadj = self.pic_scroll.get_vadjustment()
        self.start_hadj = hadj.get_value() if hadj else 0.0
        self.start_vadj = vadj.get_value() if vadj else 0.0
        self.canvas_box.set_cursor_from_name("grabbing")

    def on_drag_update(self, gesture, offset_x, offset_y):
        """Pan view smoothly as user drags."""
        hadj = self.pic_scroll.get_hadjustment()
        vadj = self.pic_scroll.get_vadjustment()
        if hadj:
            hadj.set_value(self.start_hadj - offset_x)
        if vadj:
            vadj.set_value(self.start_vadj - offset_y)

    def on_drag_end(self, gesture, offset_x, offset_y):
        """Reset cursor after dragging."""
        self.canvas_box.set_cursor_from_name("default")

    def _worker_render(self):
        try:
            png_bytes = fetch_or_render_mermaid_png(self.code)
            GLib.idle_add(self._on_rendered, png_bytes)
        except Exception as e:
            GLib.idle_add(self._on_render_error, str(e))

    def _on_rendered(self, png_bytes: bytes):
        self.spinner.stop()
        self.spinner_box.set_visible(False)
        try:
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(png_bytes)
            loader.close()
            self.pixbuf_orig = loader.get_pixbuf()
            self._apply_pixbuf()
            self.pic_scroll.set_visible(True)
        except Exception:
            self.stack.set_visible_child_name("source")
        return False

    def _on_render_error(self, err_msg: str):
        self.spinner.stop()
        self.spinner_box.set_visible(False)
        self.stack.set_visible_child_name("source")
        return False

    def _apply_pixbuf(self):
        if not self.pixbuf_orig:
            return
        w = max(1, int(self.pixbuf_orig.get_width() * self.zoom))
        h = max(1, int(self.pixbuf_orig.get_height() * self.zoom))
        scaled = self.pixbuf_orig.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        if scaled:
            texture = Gdk.Texture.new_for_pixbuf(scaled)
            self.picture.set_paintable(texture)
            self.btn_zoom_reset.set_label(f"{int(self.zoom * 100)}%")

    def adjust_zoom(self, factor: float):
        self.set_zoom(max(0.3, min(3.5, self.zoom * factor)))

    def set_zoom(self, value: float):
        self.zoom = value
        self._apply_pixbuf()

    def on_toggle_source(self, btn):
        if btn.get_active():
            self.stack.set_visible_child_name("source")
        else:
            self.stack.set_visible_child_name("diagram")

    def on_copy(self, btn):
        display = Gdk.Display.get_default()
        if display:
            display.get_clipboard().set(self.code)
            btn.set_label("Copied!")
            GLib.timeout_add(1300, lambda: (btn.set_label("Copy"), False)[1])


def inline_tokens_to_pango_markup(children) -> str:
    """Convert markdown-it inline tokens into safe Pango markup."""
    if not children:
        return ""
    parts = []
    for tok in children:
        ttype = tok.type
        if ttype == "text":
            parts.append(html.escape(tok.content))
        elif ttype == "code_inline":
            escaped = html.escape(tok.content)
            parts.append(
                f'<span font_family="monospace" background="#313244" foreground="#f38ba8"> {escaped} </span>'
            )
        elif ttype == "strong_open":
            parts.append("<b>")
        elif ttype == "strong_close":
            parts.append("</b>")
        elif ttype == "em_open":
            parts.append("<i>")
        elif ttype == "em_close":
            parts.append("</i>")
        elif ttype == "s_open":
            parts.append("<s>")
        elif ttype == "s_close":
            parts.append("</s>")
        elif ttype == "link_open":
            href = ""
            if tok.attrs and "href" in tok.attrs:
                href = html.escape(str(tok.attrs["href"]), quote=True)
            parts.append(f'<a href="{href}">')
        elif ttype == "link_close":
            parts.append("</a>")
        elif ttype == "softbreak":
            parts.append("\n")
        elif ttype == "hardbreak":
            parts.append("\n")
        elif ttype == "image":
            alt = html.escape(tok.content or "image")
            parts.append(f'<span foreground="#89b4fa">[🖼 {alt}]</span>')
        elif ttype == "html_inline":
            raw_tag = tok.content.strip().lower()
            if raw_tag in ("<br>", "<br/>", "<br />"):
                parts.append("\n")
            elif raw_tag == "<kbd>":
                parts.append('<span font_family="monospace" background="#45475a" foreground="#cdd6f4"> ')
            elif raw_tag == "</kbd>":
                parts.append(" </span>")
            else:
                parts.append(html.escape(tok.content))
    return "".join(parts)


class MarkdownViewer(Gtk.Box):
    """Rich Preview viewer for Markdown (.md) and Mermaid (.mmd, .mermaid) files."""

    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        ensure_markdown_css()

        self.file_path = file_path
        self.base_dir = os.path.dirname(os.path.abspath(file_path))
        self.raw_content = ""
        self.raw_viewer_loaded = False
        self.raw_viewer = None

        # Top Toolbar
        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.toolbar.add_css_class("code-toolbar")

        self.lbl_badge = Gtk.Label(label="PREVIEW")
        self.lbl_badge.add_css_class("code-lang-badge")
        self.toolbar.append(self.lbl_badge)

        self.lbl_meta = Gtk.Label(label="")
        self.lbl_meta.add_css_class("code-meta-label")
        self.lbl_meta.set_halign(Gtk.Align.START)
        self.lbl_meta.set_hexpand(True)
        self.toolbar.append(self.lbl_meta)

        # Mode switch buttons: Preview (default) vs Raw Code
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_mode_preview = Gtk.ToggleButton(label="Preview")
        self.btn_mode_preview.add_css_class("code-btn-small")
        self.btn_mode_preview.set_active(True)

        self.btn_mode_raw = Gtk.ToggleButton(label="Raw Code")
        self.btn_mode_raw.add_css_class("code-btn-small")
        self.btn_mode_raw.set_group(self.btn_mode_preview)

        self.btn_mode_preview.connect("toggled", self.on_mode_toggled)
        mode_box.append(self.btn_mode_preview)
        mode_box.append(self.btn_mode_raw)
        self.toolbar.append(mode_box)

        # Copy button
        self.btn_copy = Gtk.Button(label="Copy")
        self.btn_copy.add_css_class("code-btn-small")
        self.btn_copy.connect("clicked", self.on_copy_clicked)
        self.toolbar.append(self.btn_copy)

        self.append(self.toolbar)

        # Stack: "preview" (default) vs "raw"
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.append(self.stack)

        # Preview Scrolled Page
        self.preview_scroll = Gtk.ScrolledWindow()
        self.preview_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.preview_scroll.add_css_class("md-page-bg")
        self.preview_scroll.set_hexpand(True)
        self.preview_scroll.set_vexpand(True)

        self.outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.outer_box.set_margin_start(28)
        self.outer_box.set_margin_end(28)
        self.outer_box.set_margin_top(20)
        self.outer_box.set_margin_bottom(24)

        self.doc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.doc_box.add_css_class("md-content-column")
        self.outer_box.append(self.doc_box)

        self.preview_scroll.set_child(self.outer_box)
        self.stack.add_named(self.preview_scroll, "preview")

        # Raw Code Page container (lazily populated when user clicks Raw Code)
        self.raw_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_named(self.raw_container, "raw")

        self.load_file()

    def load_file(self):
        try:
            size = os.path.getsize(self.file_path)
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                self.raw_content = f.read(1024 * 1024)

            ext = os.path.splitext(self.file_path)[1].lower()
            is_standalone_mermaid = ext in (".mmd", ".mermaid") or is_mermaid_content(self.raw_content)

            if is_standalone_mermaid:
                self.lbl_badge.set_text("MERMAID PREVIEW")
                lines = self.raw_content.count("\n") + 1
                self.lbl_meta.set_text(
                    f"{detect_mermaid_diagram_type(self.raw_content)}  •  {lines:,} lines  •  {format_size(size)}"
                )
                self.doc_box.append(MermaidDiagramCard(self.raw_content))
            else:
                self.lbl_badge.set_text("MARKDOWN PREVIEW")
                self._render_markdown(self.raw_content, size)

            self.stack.set_visible_child_name("preview")

        except Exception as e:
            err = Gtk.Label(label=f"Could not render preview:\n{e}")
            self.doc_box.append(err)

    def _render_markdown(self, content: str, size: int):
        if not HAS_MARKDOWN_IT:
            lbl = Gtk.Label(label=content)
            lbl.set_wrap(True)
            lbl.set_selectable(True)
            self.doc_box.append(lbl)
            return

        md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
        tokens = md.parse(content)

        mermaid_count = 0
        code_count = 0
        heading_count = 0

        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]
            ttype = tok.type

            # 1. Headings
            if ttype == "heading_open":
                level = tok.tag  # h1..h6
                heading_count += 1
                inline_tok = tokens[i + 1] if (i + 1 < n and tokens[i + 1].type == "inline") else None
                markup = inline_tokens_to_pango_markup(inline_tok.children if inline_tok else [])
                lbl = self._create_markup_label(markup, css_class=f"md-{level}")
                lbl.set_margin_top(10 if level in ("h1", "h2") else 6)
                self.doc_box.append(lbl)

                if level in ("h1", "h2"):
                    rule = Gtk.Box()
                    rule.add_css_class("md-heading-rule")
                    rule.set_margin_bottom(4)
                    self.doc_box.append(rule)

                i += 3
                continue

            # 2. Paragraphs
            if ttype == "paragraph_open":
                inline_tok = tokens[i + 1] if (i + 1 < n and tokens[i + 1].type == "inline") else None
                if inline_tok:
                    # Check if paragraph contains standalone image token
                    img_tokens = [c for c in (inline_tok.children or []) if c.type == "image"]
                    for img_t in img_tokens:
                        src = img_t.attrs.get("src", "") if img_t.attrs else ""
                        self._try_append_local_image(src)

                    markup = inline_tokens_to_pango_markup(inline_tok.children)
                    if markup.strip():
                        lbl = self._create_markup_label(markup, css_class="md-paragraph")
                        self.doc_box.append(lbl)
                i += 3
                continue

            # 3. Fenced Code Blocks & Mermaid Blocks
            if ttype in ("fence", "code_block"):
                info = (tok.info or "").strip().split()[0].lower() if tok.info else ""
                code_text = tok.content.rstrip("\n")
                if info in ("mermaid", "mmd") or is_mermaid_content(code_text):
                    mermaid_count += 1
                    self.doc_box.append(MermaidDiagramCard(code_text))
                else:
                    code_count += 1
                    self.doc_box.append(self._create_code_block_card(code_text, info))
                i += 1
                continue

            # 4. Blockquotes & GitHub Alerts ([!NOTE], [!TIP], [!IMPORTANT], [!WARNING], [!CAUTION])
            if ttype == "blockquote_open":
                end_i = self._find_matching_close(tokens, i, "blockquote_open", "blockquote_close")
                inner_tokens = tokens[i + 1 : end_i]
                self.doc_box.append(self._build_blockquote_widget(inner_tokens))
                i = end_i + 1
                continue

            # 5. Bullet & Ordered Lists
            if ttype in ("bullet_list_open", "ordered_list_open"):
                close_type = "bullet_list_close" if ttype == "bullet_list_open" else "ordered_list_close"
                end_i = self._find_matching_close(tokens, i, ttype, close_type)
                is_ordered = ttype == "ordered_list_open"
                self.doc_box.append(self._build_list_widget(tokens[i + 1 : end_i], is_ordered))
                i = end_i + 1
                continue

            # 6. Tables
            if ttype == "table_open":
                end_i = self._find_matching_close(tokens, i, "table_open", "table_close")
                self.doc_box.append(self._build_table_widget(tokens[i + 1 : end_i]))
                i = end_i + 1
                continue

            # 7. Horizontal Rule
            if ttype == "hr":
                hr = Gtk.Box()
                hr.add_css_class("md-hr")
                self.doc_box.append(hr)
                i += 1
                continue

            i += 1

        lines = content.count("\n") + 1
        meta_parts = [f"{lines:,} lines"]
        if heading_count:
            meta_parts.append(f"{heading_count} sections")
        if mermaid_count:
            meta_parts.append(f"{mermaid_count} Mermaid diagram{'s' if mermaid_count > 1 else ''}")
        if code_count:
            meta_parts.append(f"{code_count} code block{'s' if code_count > 1 else ''}")
        meta_parts.append(format_size(size))
        self.lbl_meta.set_text("  •  ".join(meta_parts))

    def _find_matching_close(self, tokens, start_idx: int, open_type: str, close_type: str) -> int:
        depth = 0
        for idx in range(start_idx, len(tokens)):
            if tokens[idx].type == open_type:
                depth += 1
            elif tokens[idx].type == close_type:
                depth -= 1
                if depth == 0:
                    return idx
        return len(tokens) - 1

    def _create_markup_label(
        self,
        markup: str,
        css_class: str = None,
        wrap: bool = True,
        wrap_mode: Pango.WrapMode = Pango.WrapMode.WORD,
    ) -> Gtk.Label:
        lbl = Gtk.Label()
        if css_class:
            lbl.add_css_class(css_class)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_valign(Gtk.Align.START)
        lbl.set_xalign(0.0)
        lbl.set_wrap(wrap)
        lbl.set_wrap_mode(wrap_mode)
        lbl.set_selectable(True)
        try:
            lbl.set_markup(markup)
        except Exception:
            lbl.set_text(re.sub(r"<[^>]+>", "", markup))
        return lbl

    def _create_code_block_card(self, code_text: str, lang_info: str) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("md-code-card")
        card.set_margin_top(4)
        card.set_margin_bottom(4)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("md-code-card-header")

        lbl_lang = Gtk.Label(label=(lang_info or "code").upper())
        lbl_lang.add_css_class("code-lang-badge")
        header.append(lbl_lang)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        btn_copy = Gtk.Button(label="Copy")
        btn_copy.add_css_class("code-btn-small")

        def _copy_block(_btn):
            display = Gdk.Display.get_default()
            if display:
                display.get_clipboard().set(code_text)
                btn_copy.set_label("Copied!")
                GLib.timeout_add(1300, lambda: (btn_copy.set_label("Copy"), False)[1])

        btn_copy.connect("clicked", _copy_block)
        header.append(btn_copy)
        card.append(header)

        tv = Gtk.TextView()
        tv.add_css_class("md-code-block-view")
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_left_margin(14)
        tv.set_right_margin(14)
        tv.set_top_margin(10)
        tv.set_bottom_margin(10)
        tv.set_pixels_above_lines(2)
        tv.set_pixels_below_lines(2)

        detected_label = highlight_buffer_with_pygments(
            tv.get_buffer(), code_text, lang_hint=lang_info or "text"
        )
        lbl_lang.set_text(detected_label)
        card.append(tv)
        return card

    def _build_blockquote_widget(self, inner_tokens) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inline_markups = []
        for t in inner_tokens:
            if t.type == "inline" and t.children:
                inline_markups.append(inline_tokens_to_pango_markup(t.children))

        full_markup = "\n".join(inline_markups).strip()
        alert_map = {
            "[!NOTE]": ("md-alert-note", "#89b4fa", "ℹ  NOTE"),
            "[!TIP]": ("md-alert-tip", "#a6e3a1", "💡  TIP"),
            "[!IMPORTANT]": ("md-alert-important", "#cba6f7", "❗  IMPORTANT"),
            "[!WARNING]": ("md-alert-warning", "#f9e2af", "⚠  WARNING"),
            "[!CAUTION]": ("md-alert-caution", "#f38ba8", "🛑  CAUTION"),
        }

        matched_alert = None
        for prefix, meta in alert_map.items():
            if full_markup.upper().startswith(prefix):
                matched_alert = meta
                full_markup = full_markup[len(prefix):].lstrip("\n ")
                break

        if matched_alert:
            css_cls, color, title_text = matched_alert
            box.add_css_class(css_cls)
            title_lbl = self._create_markup_label(
                f'<span foreground="{color}" weight="bold">{html.escape(title_text)}</span>'
            )
            box.append(title_lbl)
        else:
            box.add_css_class("md-blockquote")

        if full_markup:
            box.append(self._create_markup_label(full_markup, css_class="md-paragraph"))
        return box

    def _build_list_widget(self, inner_tokens, is_ordered: bool, depth: int = 0) -> Gtk.Widget:
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_margin_start(8 if depth == 0 else 20)
        if depth > 0:
            list_box.set_margin_top(4)

        item_idx = 0
        i = 0
        n = len(inner_tokens)
        while i < n:
            if inner_tokens[i].type == "list_item_open":
                end_i = self._find_matching_close(
                    inner_tokens, i, "list_item_open", "list_item_close"
                )
                item_idx += 1
                item_tokens = inner_tokens[i + 1 : end_i]

                item_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_valign(Gtk.Align.START)

                # Separate direct inline tokens from nested lists
                direct_markups = []
                nested_widgets = []
                j = 0
                m = len(item_tokens)
                while j < m:
                    itok = item_tokens[j]
                    if itok.type in ("bullet_list_open", "ordered_list_open"):
                        close_t = (
                            "bullet_list_close"
                            if itok.type == "bullet_list_open"
                            else "ordered_list_close"
                        )
                        sub_end = self._find_matching_close(item_tokens, j, itok.type, close_t)
                        nested_widgets.append(
                            self._build_list_widget(
                                item_tokens[j + 1 : sub_end],
                                itok.type == "ordered_list_open",
                                depth + 1,
                            )
                        )
                        j = sub_end + 1
                        continue
                    elif itok.type == "inline" and itok.children:
                        direct_markups.append(inline_tokens_to_pango_markup(itok.children))
                    j += 1

                body_markup = "\n".join(direct_markups).strip()

                bullet_char = "•" if depth == 0 else "◦"
                bullet_markup = (
                    f'<span foreground="#89b4fa" weight="bold">{item_idx}.</span>'
                    if is_ordered
                    else f'<span foreground="#89b4fa" weight="bold">{bullet_char}</span>'
                )
                if body_markup.startswith("[x] ") or body_markup.startswith("[X] "):
                    bullet_markup = '<span foreground="#a6e3a1" weight="bold">☑</span>'
                    body_markup = body_markup[4:]
                elif body_markup.startswith("[ ] "):
                    bullet_markup = '<span foreground="#9399b2" weight="bold">☐</span>'
                    body_markup = body_markup[4:]

                lbl_bullet = self._create_markup_label(bullet_markup, wrap=False)
                lbl_bullet.set_selectable(False)
                row.append(lbl_bullet)

                lbl_body = self._create_markup_label(body_markup, css_class="md-paragraph")
                lbl_body.set_hexpand(True)
                row.append(lbl_body)

                item_vbox.append(row)
                for nw in nested_widgets:
                    item_vbox.append(nw)

                list_box.append(item_vbox)
                i = end_i + 1
                continue
            i += 1

        return list_box

    def _build_table_widget(self, table_tokens) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.add_css_class("md-table-card")
        grid.set_hexpand(True)
        grid.set_valign(Gtk.Align.START)
        grid.set_margin_top(6)
        grid.set_margin_bottom(6)

        rows = []
        cur_row = []
        in_header = False
        cur_align = "left"

        for tok in table_tokens:
            if tok.type == "thead_open":
                in_header = True
            elif tok.type == "thead_close":
                in_header = False
            elif tok.type == "tr_open":
                cur_row = []
            elif tok.type in ("th_open", "td_open"):
                cur_align = "left"
                if tok.attrs and "style" in tok.attrs:
                    style_str = str(tok.attrs["style"]).lower()
                    if "center" in style_str:
                        cur_align = "center"
                    elif "right" in style_str:
                        cur_align = "right"
            elif tok.type == "inline":
                cur_row.append((inline_tokens_to_pango_markup(tok.children), in_header, cur_align))
            elif tok.type == "tr_close":
                if cur_row:
                    rows.append(cur_row)

        if not rows:
            return grid

        num_cols = max(len(r) for r in rows)
        col_max_len = [0] * num_cols

        for row in rows:
            for c_idx, (cell_markup, _, _) in enumerate(row):
                plain = re.sub(r"<[^>]+>", "", cell_markup)
                longest_line = max((len(line.strip()) for line in plain.splitlines()), default=0)
                if longest_line > col_max_len[c_idx]:
                    col_max_len[c_idx] = longest_line

        # Determine which columns should expand horizontally
        expand_cols = {c for c, mlen in enumerate(col_max_len) if mlen > 42}
        if not expand_cols and num_cols > 0:
            widest_col = max(range(num_cols), key=lambda c: col_max_len[c])
            expand_cols.add(widest_col)

        for r_idx, row in enumerate(rows):
            for c_idx, (cell_markup, is_hdr, align) in enumerate(row):
                col_len = col_max_len[c_idx]
                should_expand = c_idx in expand_cols
                is_short_col = col_len <= 26 and not should_expand

                cell_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                cell_box.set_hexpand(should_expand)
                cell_box.set_vexpand(False)
                cell_box.set_halign(Gtk.Align.FILL)
                cell_box.set_valign(Gtk.Align.FILL)

                if is_hdr:
                    cell_box.add_css_class("md-table-header-cell")
                    styled_markup = f"<b>{cell_markup}</b>"
                else:
                    cell_box.add_css_class(
                        "md-table-cell-even" if r_idx % 2 == 0 else "md-table-cell-odd"
                    )
                    styled_markup = cell_markup

                lbl = self._create_markup_label(
                    styled_markup,
                    css_class="md-paragraph",
                    wrap=not is_short_col,
                    wrap_mode=Pango.WrapMode.WORD,
                )
                lbl.set_hexpand(should_expand)
                lbl.set_valign(Gtk.Align.CENTER if is_short_col or is_hdr else Gtk.Align.START)

                if align == "center":
                    lbl.set_xalign(0.5)
                    lbl.set_halign(Gtk.Align.CENTER)
                elif align == "right":
                    lbl.set_xalign(1.0)
                    lbl.set_halign(Gtk.Align.END)
                else:
                    lbl.set_xalign(0.0)
                    lbl.set_halign(Gtk.Align.FILL if should_expand else Gtk.Align.START)

                # Reserve comfortable minimum width for medium columns (e.g. Title / Criteria column)
                if not is_short_col and not should_expand:
                    lbl.set_width_chars(min(max(col_len, 18), 28))
                    lbl.set_max_width_chars(34)

                cell_box.append(lbl)
                grid.attach(cell_box, c_idx, r_idx, 1, 1)

        return grid

    def _try_append_local_image(self, src: str):
        if not src or src.startswith(("http://", "https://", "data:")):
            return
        candidate = src if os.path.isabs(src) else os.path.join(self.base_dir, src)
        if os.path.exists(candidate):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(candidate)
                pic = Gtk.Picture.new_for_pixbuf(pb)
                pic.set_can_shrink(True)
                pic.set_halign(Gtk.Align.START)
                pic.set_size_request(-1, min(pb.get_height(), 420))
                self.doc_box.append(pic)
            except Exception:
                pass

    def on_mode_toggled(self, btn):
        if self.btn_mode_preview.get_active():
            self.stack.set_visible_child_name("preview")
        else:
            if not self.raw_viewer_loaded:
                self.raw_viewer = TextViewer(
                    self.file_path, raw_content=self.raw_content, show_toolbar=False
                )
                self.raw_container.append(self.raw_viewer)
                self.raw_viewer_loaded = True
            self.stack.set_visible_child_name("raw")

    def on_copy_clicked(self, btn):
        display = Gdk.Display.get_default()
        if display and self.raw_content:
            display.get_clipboard().set(self.raw_content)
            btn.set_label("Copied!")
            GLib.timeout_add(1400, lambda: (btn.set_label("Copy"), False)[1])

    def toggle_search(self):
        if not self.raw_viewer_loaded or self.stack.get_visible_child_name() != "raw":
            self.btn_mode_raw.set_active(True)
        if self.raw_viewer:
            self.raw_viewer.toggle_search()

    def close_search(self):
        if self.raw_viewer:
            self.raw_viewer.close_search()

    def is_search_open(self) -> bool:
        if self.raw_viewer:
            return self.raw_viewer.is_search_open()
        return False

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        lines = self.raw_content.count("\n") + 1 if self.raw_content else 20
        content_h = 160 + int(lines * 22)
        min_h = 420
        max_h = min(980, int(screen_h * 0.82))
        return target_w, max(min_h, min(max_h, content_h))
