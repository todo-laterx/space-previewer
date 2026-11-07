import os
import re
import io
import json
import logging
import zlib
import base64
import hashlib
import threading
import urllib.parse
import urllib.request
import html
import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango, PangoCairo, Adw

try:
    from markdown_it import MarkdownIt
    HAS_MARKDOWN_IT = True
except ImportError:
    HAS_MARKDOWN_IT = False

from utils.formatters import format_size
from utils.i18n import _, ngettext
from utils.parsers import MERMAID_KEYWORDS, is_mermaid_content
from utils.quote import format_line_reference
from widgets.quote_bar import QuoteBar
from .markdown_search import MarkdownSearch
from .text_viewer import (
    TextViewer,
    ensure_code_viewer_css,
    highlight_buffer_with_pygments,
    is_dark_theme,
    hex_to_rgb,
    split_at_byte_limit,
    ACCENT_LIGHT,
    ACCENT_DARK,
    CODE_SURFACE_LIGHT,
    CODE_SURFACE_DARK,
    CODE_TEXT_LIGHT,
    CODE_TEXT_DARK,
)

_MD_CSS_INSTALLED = False
_MD_CSS_PROVIDER = None
_MD_DARK_HANDLER_CONNECTED = False

logger = logging.getLogger(__name__)

# Documented untrusted-input limits (SECURITY.md). Files are read as bytes
# and capped before decoding; code blocks above the highlight cap keep their
# tail as plain text instead of being sent through Pygments.
MARKDOWN_READ_LIMIT = 2 * 1024 * 1024
MARKDOWN_ASYNC_READ_THRESHOLD = 1024 * 1024
CODE_BLOCK_HIGHLIGHT_LIMIT = 512 * 1024
_READ_CHUNK_SIZE = 64 * 1024

MARKDOWN_VIEWER_CSS = """
@define-color sp_accent %(accent)s;
@define-color sp_code_surface %(code_surface)s;
@define-color sp_code_text %(code_text)s;

.md-page-bg {
    background-color: @window_bg_color;
}
.md-content-column {
    background-color: transparent;
    padding: 28px 36px;
}
.md-h1 {
    font-size: 26px;
    font-weight: 800;
    color: @window_fg_color;
}
.md-h2 {
    font-size: 21px;
    font-weight: 700;
    color: @window_fg_color;
}
.md-h3 {
    font-size: 17px;
    font-weight: 700;
    color: alpha(@window_fg_color, 0.88);
}
.md-h4 {
    font-size: 15px;
    font-weight: 700;
    color: alpha(@window_fg_color, 0.78);
}
.md-h5, .md-h6 {
    font-size: 13px;
    font-weight: 700;
    color: alpha(@window_fg_color, 0.68);
}
.md-heading-rule {
    background-color: @borders;
    min-height: 1px;
}
.md-paragraph {
    font-size: 14px;
    line-height: 1.48;
    color: @window_fg_color;
}
.md-blockquote {
    background-color: alpha(@view_fg_color, 0.05);
    border-left: 4px solid @sp_accent;
    border-radius: 0 8px 8px 0;
    padding: 10px 16px;
}
.md-alert-note {
    background-color: alpha(%(alert_note)s, 0.10);
    border-left: 4px solid %(alert_note)s;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-tip {
    background-color: alpha(%(alert_tip)s, 0.10);
    border-left: 4px solid %(alert_tip)s;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-important {
    background-color: alpha(%(alert_important)s, 0.10);
    border-left: 4px solid %(alert_important)s;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-warning {
    background-color: alpha(%(alert_warning)s, 0.10);
    border-left: 4px solid %(alert_warning)s;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-alert-caution {
    background-color: alpha(%(alert_caution)s, 0.10);
    border-left: 4px solid %(alert_caution)s;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
}
.md-code-card {
    background-color: @sp_code_surface;
    border: 1px solid @borders;
    border-radius: 10px;
}
.md-code-card-header {
    background-color: transparent;
    border-bottom: 1px solid @borders;
    border-radius: 10px 10px 0 0;
    padding: 6px 14px;
}
.md-code-card-header .code-lang-badge {
    color: %(badge_fg)s;
    background-color: %(badge_bg)s;
    border-color: %(badge_border)s;
}
.md-mermaid-badge {
    background-color: %(badge_bg)s;
    color: %(badge_fg)s;
    border: 1px solid %(badge_border)s;
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 11px;
}
.md-code-block-view {
    background-color: @sp_code_surface;
    color: @sp_code_text;
    font-family: "Adwaita Mono", "JetBrains Mono", "Source Code Pro", monospace;
    font-size: 12.5px;
    border-radius: 0 0 10px 10px;
}
.md-code-block-view text {
    background-color: @sp_code_surface;
    color: @sp_code_text;
}
.md-mermaid-card {
    background-color: @view_bg_color;
    border: 1px solid @borders;
    border-radius: 10px;
}
.md-mermaid-header {
    background-color: transparent;
    border-bottom: 1px solid @borders;
    border-radius: 10px 10px 0 0;
    padding: 6px 14px;
}
.md-mermaid-canvas {
    background-color: @view_bg_color;
    border-radius: 0 0 10px 10px;
    padding: 16px;
}
.md-table-card {
    background-color: @view_bg_color;
    border: 1px solid @borders;
    border-radius: 8px;
}
.md-table-header-cell {
    background-color: alpha(@view_fg_color, 0.08);
    border-bottom: 1px solid @borders;
    border-right: 1px solid @borders;
    padding: 8px 14px;
}
.md-table-cell-even {
    background-color: alpha(@view_fg_color, 0.03);
    border-bottom: 1px solid @borders;
    border-right: 1px solid @borders;
    padding: 7px 14px;
}
.md-table-cell-odd {
    background-color: transparent;
    border-bottom: 1px solid @borders;
    border-right: 1px solid @borders;
    padding: 7px 14px;
}
.md-hr {
    background-color: @borders;
    min-height: 2px;
    margin-top: 8px;
    margin-bottom: 8px;
}
.md-quote-hover {
    background-color: alpha(@sp_accent, 0.06);
    outline: 1px solid alpha(@sp_accent, 0.28);
    outline-offset: 4px;
    border-radius: 6px;
}
.md-quote-active {
    background-color: alpha(@sp_accent, 0.14);
    outline: 1.5px solid alpha(@sp_accent, 0.62);
    outline-offset: 4px;
    border-radius: 6px;
}
.md-quote-plus-badge {
    background-color: #2F81F7;
    color: #FFFFFF;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 800;
    min-width: 18px;
    min-height: 18px;
    padding: 0 4px;
}
"""

_NERD_FONT_REGISTERED = False


def _ensure_nerd_font_registered() -> None:
    """Register bundled SymbolsNerdFont-Regular.ttf with Fontconfig once."""
    global _NERD_FONT_REGISTERED
    if _NERD_FONT_REGISTERED:
        return
    _NERD_FONT_REGISTERED = True
    try:
        import ctypes

        font_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "assets",
                "SymbolsNerdFont-Regular.ttf",
            )
        )
        if not os.path.isfile(font_path):
            return
        fc = ctypes.CDLL("libfontconfig.so.1")
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        cfg = fc.FcConfigGetCurrent()
        if cfg:
            fc.FcConfigAppFontAddFile(cfg, font_path.encode("utf-8"))
    except Exception:
        logger.debug("Could not register bundled Nerd Font symbols", exc_info=True)


def _alert_palette(dark: bool) -> dict:
    """Muted semantic colours for Markdown alert titles; no purple or neon."""
    accent = ACCENT_DARK if dark else ACCENT_LIGHT
    return {
        "note": accent,
        "tip": "#7FB89A" if dark else "#3F7A5A",
        "important": accent,
        "warning": "#D4B36A" if dark else "#8A6D2F",
        "caution": "#D08989" if dark else "#A34A4A",
    }


def _badge_palette(dark: bool) -> dict:
    """High-contrast badge colours that stay readable on a dark surface."""
    if dark:
        return {
            "bg": "alpha(@sp_accent, 0.26)",
            "fg": "#D6E4FF",
            "border": "alpha(@sp_accent, 0.65)",
        }
    return {
        "bg": "alpha(@sp_accent, 0.16)",
        "fg": "#243F86",
        "border": "alpha(@sp_accent, 0.45)",
    }


def _render_markdown_css(dark: bool) -> str:
    alerts = _alert_palette(dark)
    badge = _badge_palette(dark)
    return MARKDOWN_VIEWER_CSS % {
        "accent": ACCENT_DARK if dark else ACCENT_LIGHT,
        "code_surface": CODE_SURFACE_DARK if dark else CODE_SURFACE_LIGHT,
        "code_text": CODE_TEXT_DARK if dark else CODE_TEXT_LIGHT,
        "alert_note": alerts["note"],
        "alert_tip": alerts["tip"],
        "alert_important": alerts["important"],
        "alert_warning": alerts["warning"],
        "alert_caution": alerts["caution"],
        "badge_bg": badge["bg"],
        "badge_fg": badge["fg"],
        "badge_border": badge["border"],
    }


def _reload_markdown_css(*_args) -> None:
    if _MD_CSS_PROVIDER is not None:
        _MD_CSS_PROVIDER.load_from_data(
            _render_markdown_css(is_dark_theme()).encode("utf-8")
        )


def ensure_markdown_css():
    global _MD_CSS_INSTALLED, _MD_CSS_PROVIDER, _MD_DARK_HANDLER_CONNECTED
    _ensure_nerd_font_registered()
    ensure_code_viewer_css()
    if _MD_CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    if _MD_CSS_PROVIDER is None:
        _MD_CSS_PROVIDER = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            display, _MD_CSS_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    _MD_CSS_PROVIDER.load_from_data(
        _render_markdown_css(is_dark_theme()).encode("utf-8")
    )
    if not _MD_DARK_HANDLER_CONNECTED:
        manager = Adw.StyleManager.get_default()
        if manager is not None:
            manager.connect("notify::dark", _reload_markdown_css)
            _MD_DARK_HANDLER_CONNECTED = True
    _MD_CSS_INSTALLED = True


def detect_mermaid_diagram_type(code: str) -> str:
    stripped = code.lstrip()
    while stripped.startswith("%%"):
        nl = stripped.find("\n")
        if nl == -1:
            break
        stripped = stripped[nl + 1:].lstrip()
    first_word = stripped.split()[0] if stripped.split() else "Diagram"
    mapping = {
        "flowchart": _("Flowchart"),
        "graph": _("Flowchart Graph"),
        "sequenceDiagram": _("Sequence Diagram"),
        "classDiagram": _("Class Diagram"),
        "stateDiagram": _("State Diagram"),
        "stateDiagram-v2": _("State Diagram"),
        "erDiagram": _("ER Diagram"),
        "gantt": _("Gantt Chart"),
        "pie": _("Pie Chart"),
        "mindmap": _("Mindmap"),
        "journey": _("User Journey"),
        "gitGraph": _("Git Graph"),
        "timeline": _("Timeline"),
        "xychart-beta": _("XY Chart"),
    }
    return mapping.get(first_word, _("Mermaid Diagram"))


def render_mermaid_offline_cairo(code: str, dark=None) -> bytes:
    """Offline fallback diagram renderer using Cairo + Pango so diagrams still preview offline."""
    nodes = {}
    edges = []
    if dark is None:
        dark = is_dark_theme()
    surface_rgb = hex_to_rgb(CODE_SURFACE_DARK if dark else CODE_SURFACE_LIGHT)
    text_rgb = hex_to_rgb(CODE_TEXT_DARK if dark else CODE_TEXT_LIGHT)
    accent_rgb = hex_to_rgb(ACCENT_DARK if dark else ACCENT_LIGHT)
    node_rgb = tuple(
        (surface * 0.9) + (text * 0.1)
        for surface, text in zip(surface_rgb, text_rgb)
    )

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
        cr.set_source_rgb(*surface_rgb)
        cr.paint()
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 11"))
        cr.set_source_rgb(*accent_rgb)
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
    cr.set_source_rgb(*surface_rgb)
    cr.paint()

    positions = {}
    for idx, (nid, _label) in enumerate(node_list):
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
            cr.set_source_rgba(*accent_rgb, 0.75)
            cr.move_to(sx, sy)
            cr.line_to(dx, dy)
            cr.stroke()

    # Draw nodes
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 10.5"))
    for nid, label in node_list:
        x, y = positions[nid]
        cr.set_source_rgb(*node_rgb)
        cr.rectangle(x, y, box_w, box_h)
        cr.fill_preserve()
        cr.set_source_rgb(*accent_rgb)
        cr.set_line_width(1.8)
        cr.stroke()

        layout.set_text(label[:26], -1)
        _, log = layout.get_pixel_extents()
        tx = x + max(8, (box_w - log.width) / 2)
        ty = y + max(6, (box_h - log.height) / 2)
        cr.set_source_rgb(*text_rgb)
        cr.move_to(tx, ty)
        PangoCairo.show_layout(cr, layout)

    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def network_allowed() -> bool:
    """Return True only when the user explicitly opted into network rendering.

    Mermaid diagrams render locally by default. The remote renderer is a last
    resort for diagram types the offline renderer cannot draw, and it sends the
    diagram source to a third party, so it stays behind an explicit env opt-in.
    """
    return os.environ.get("SPACE_PREVIEWER_ALLOW_NETWORK", "").strip() == "1"


def fetch_or_render_mermaid_png(code: str, cancel_event=None, dark=None) -> bytes:
    """Render Mermaid diagram to PNG bytes instantly via cache or high-speed Cairo renderer.

    ``cancel_event`` is checked before and after the mermaid.ink request so a
    viewer teardown can discard an in-flight network response.
    """
    cleaned = code.strip()
    if dark is None:
        dark = is_dark_theme()
    theme_key = "dark" if dark else "light"
    cache_dir = os.path.expanduser("~/.cache/space-previewer/mermaid")
    os.makedirs(cache_dir, exist_ok=True)
    digest = hashlib.sha256(f"{theme_key}:{cleaned}".encode("utf-8")).hexdigest()[:24]
    cache_path = os.path.join(cache_dir, f"{digest}.png")

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    if cancelled():
        return b""

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
        with open(cache_path, "rb") as f:
            return f.read()

    # 1. Fast local rendering via Cairo (instant ~12ms, zero network lag)
    try:
        data = render_mermaid_offline_cairo(cleaned, dark)
        if data and data.startswith(b"\x89PNG"):
            if cancelled():
                return b""
            with open(cache_path, "wb") as f:
                f.write(data)
            return data
    except Exception:
        logger.debug("Offline Mermaid render failed", exc_info=True)

    if cancelled():
        return b""

    # 2. Optional remote renderer. Disabled unless the user opted in with
    # SPACE_PREVIEWER_ALLOW_NETWORK=1: it sends the diagram source to a third
    # party, and the offline renderer already covers the common cases.
    if not network_allowed():
        return render_mermaid_offline_cairo(cleaned, dark)

    try:
        state = {
            "code": cleaned,
            "mermaid": json.dumps({"theme": theme_key}),
        }
        compressed = zlib.compress(json.dumps(state).encode("utf-8"), 9)
        pako = "pako:" + base64.urlsafe_b64encode(compressed).decode("ascii")
        surface = (CODE_SURFACE_DARK if dark else CODE_SURFACE_LIGHT).lstrip("#")
        url = f"https://mermaid.ink/img/{pako}?type=png&bgColor=!{surface}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            net_data = resp.read()
            if cancelled():
                return b""
            if net_data and net_data.startswith(b"\x89PNG"):
                with open(cache_path, "wb") as f:
                    f.write(net_data)
                return net_data
    except Exception:
        logger.debug("Remote Mermaid render failed", exc_info=True)

    if cancelled():
        return b""
    return render_mermaid_offline_cairo(cleaned, dark)


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
        self._cancelled = False
        self._cancel_event = threading.Event()
        self._render_thread = None
        self._copy_timeout_id = None
        self._dark = is_dark_theme()

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("md-mermaid-header")

        badge = Gtk.Label(label=_("MERMAID"))
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
        btn_zoom_out.set_tooltip_text(_("Zoom out"))
        btn_zoom_out.connect("clicked", lambda *_: self.adjust_zoom(1 / 1.2))
        header.append(btn_zoom_out)

        self.btn_zoom_reset = Gtk.Button(label="100%")
        self.btn_zoom_reset.add_css_class("code-btn-small")
        self.btn_zoom_reset.set_tooltip_text(_("Reset zoom"))
        self.btn_zoom_reset.connect("clicked", lambda *_: self.set_zoom(1.0))
        header.append(self.btn_zoom_reset)

        btn_zoom_in = Gtk.Button(label="+")
        btn_zoom_in.add_css_class("code-btn-small")
        btn_zoom_in.set_tooltip_text(_("Zoom in"))
        btn_zoom_in.connect("clicked", lambda *_: self.adjust_zoom(1.2))
        header.append(btn_zoom_in)

        # Toggle diagram vs source code
        self.btn_source = Gtk.ToggleButton(label=_("Source"))
        self.btn_source.add_css_class("code-btn-small")
        self.btn_source.set_tooltip_text(_("Show diagram source"))
        self.btn_source.connect("toggled", self.on_toggle_source)
        header.append(self.btn_source)

        btn_copy = Gtk.Button(label=_("Copy"))
        btn_copy.add_css_class("code-btn-small")
        btn_copy.set_tooltip_text(_("Copy diagram source"))
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
        lbl_loading = Gtk.Label(label=_("Rendering Mermaid diagram..."))
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
        highlight_buffer_with_pygments(
            src_tv.get_buffer(),
            self.code,
            lang_hint="mermaid",
            max_bytes=CODE_BLOCK_HIGHLIGHT_LIMIT,
        )
        self.stack.add_named(src_tv, "source")

        self.stack.set_visible_child_name("diagram")

        # Render asynchronously in background thread
        self._render_thread = threading.Thread(target=self._worker_render, daemon=True)
        self._render_thread.start()

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
            png_bytes = fetch_or_render_mermaid_png(
                self.code, self._cancel_event, self._dark
            )
            if self._cancelled or not png_bytes:
                return
            GLib.idle_add(self._on_rendered, png_bytes)
        except Exception as e:
            if not self._cancelled:
                GLib.idle_add(self._on_render_error, str(e))

    def _on_rendered(self, png_bytes: bytes):
        if self._cancelled:
            return False
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

    def _on_render_error(self, _err_msg: str):
        if self._cancelled:
            return False
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
            btn.set_label(_("Copied!"))
            if self._copy_timeout_id is not None:
                GLib.source_remove(self._copy_timeout_id)
            self._copy_timeout_id = GLib.timeout_add(
                1300, self._reset_copy_label, btn
            )

    def _reset_copy_label(self, btn):
        self._copy_timeout_id = None
        btn.set_label(_("Copy"))
        return False

    def teardown(self) -> None:
        """Cancel an in-flight mermaid.ink request and pending timers."""
        self._cancelled = True
        self._cancel_event.set()
        if self._copy_timeout_id is not None:
            GLib.source_remove(self._copy_timeout_id)
            self._copy_timeout_id = None


_FORBIDDEN_LINK_SCHEMES = re.compile(r"^(javascript|vbscript|data):", re.IGNORECASE)

_ICON_FONT_FAMILY = "CaskaydiaCove Nerd Font Propo,CaskaydiaCove Nerd Font,Symbols Nerd Font,monospace"

_EXT_NERD_ICONS: dict[str, tuple[str, str]] = {
    ".rs": ("\ue7a8", "#E06C45"),
    ".py": ("\ue606", "#3FB950"),
    ".pyw": ("\ue606", "#3FB950"),
    ".pyi": ("\ue606", "#3FB950"),
    ".js": ("\ue74e", "#F1E05A"),
    ".mjs": ("\ue74e", "#F1E05A"),
    ".cjs": ("\ue74e", "#F1E05A"),
    ".jsx": ("\ue7ba", "#61DAFB"),
    ".ts": ("\ue628", "#3178C6"),
    ".tsx": ("\ue7ba", "#3178C6"),
    ".sh": ("\uf489", "#7EE787"),
    ".bash": ("\uf489", "#7EE787"),
    ".zsh": ("\uf489", "#7EE787"),
    ".fish": ("\uf489", "#7EE787"),
    ".c": ("\ue61e", "#58A6FF"),
    ".h": ("\ue61e", "#58A6FF"),
    ".cpp": ("\ue61d", "#F34B7D"),
    ".cc": ("\ue61d", "#F34B7D"),
    ".cxx": ("\ue61d", "#F34B7D"),
    ".hpp": ("\ue61d", "#F34B7D"),
    ".hxx": ("\ue61d", "#F34B7D"),
    ".go": ("\ue627", "#00ADD8"),
    ".java": ("\ue738", "#E06C45"),
    ".jar": ("\ue738", "#E06C45"),
    ".kt": ("\ue634", "#A97BFF"),
    ".kts": ("\ue634", "#A97BFF"),
    ".swift": ("\ue755", "#F05138"),
    ".rb": ("\ue739", "#CC342D"),
    ".php": ("\ue73d", "#777BB4"),
    ".lua": ("\ue620", "#51A0CF"),
    ".html": ("\ue736", "#E34C26"),
    ".htm": ("\ue736", "#E34C26"),
    ".css": ("\ue749", "#A371F7"),
    ".scss": ("\ue749", "#A371F7"),
    ".vue": ("\ue6a0", "#41B883"),
    ".json": ("\ue60b", "#E3B341"),
    ".toml": ("\ue60b", "#E3B341"),
    ".yaml": ("\ue60b", "#E3B341"),
    ".yml": ("\ue60b", "#E3B341"),
    ".ini": ("\ue60b", "#E3B341"),
    ".conf": ("\ue60b", "#E3B341"),
    ".cfg": ("\ue60b", "#E3B341"),
    ".xml": ("\ue619", "#E37933"),
    ".svg": ("\ue619", "#E37933"),
    ".md": ("\uf48a", "#79C0FF"),
    ".mdx": ("\uf48a", "#79C0FF"),
    ".markdown": ("\uf48a", "#79C0FF"),
    ".sql": ("\ue706", "#58A6FF"),
    ".db": ("\ue706", "#58A6FF"),
    ".sqlite": ("\ue706", "#58A6FF"),
    ".apk": ("\ue70e", "#3DDC84"),
    ".service": ("\uf15b", "#8B949E"),
    ".socket": ("\uf15b", "#8B944E"),
    ".timer": ("\uf15b", "#8B949E"),
    ".desktop": ("\uf15b", "#8B949E"),
    ".rc": ("\uf15b", "#8B949E"),
    ".lock": ("\uf15b", "#8B949E"),
}

_STANDALONE_ICON_EXTS = {
    ".rs", ".py", ".pyw", ".pyi", ".js", ".mjs", ".cjs", ".jsx",
    ".ts", ".tsx", ".sh", ".bash", ".zsh", ".c", ".h", ".cpp",
    ".cc", ".hpp", ".go", ".java", ".kt", ".swift", ".rb", ".php",
    ".lua", ".html", ".css", ".scss", ".vue", ".json", ".toml",
    ".yaml", ".yml", ".md", ".mdx", ".sql", ".service",
}

_SHIELDS_COLOR_MAP = {
    "blue": "#2F81F7",
    "brightgreen": "#2EA44F",
    "green": "#2EA44F",
    "2ea44f": "#2EA44F",
    "3867d6": "#3867D6",
    "lightgrey": "#57606A",
    "lightgray": "#57606A",
    "grey": "#57606A",
    "gray": "#57606A",
    "orange": "#D19A66",
    "yellow": "#D29922",
    "red": "#CF222E",
    "critical": "#CF222E",
    "informational": "#2F81F7",
    "success": "#2EA44F",
}


def _validate_markdown_link(url: str) -> bool:
    """Allow local file:// and relative links while blocking unsafe script URIs."""
    stripped = (url or "").strip()
    return bool(stripped) and not _FORBIDDEN_LINK_SCHEMES.match(stripped)


def _extract_file_ext(candidate: str) -> tuple[str, str]:
    """Return ``(stem, lower_ext)`` for a path or URL, stripping fragments/queries."""
    if not candidate:
        return "", ""
    parsed = urllib.parse.urlparse(candidate)
    path = urllib.parse.unquote(parsed.path or candidate)
    path = re.sub(r":\d+(?:-\d+)?$", "", path.strip())
    base = os.path.basename(path.rstrip("/"))
    if not base or base.startswith("."):
        return "", ""
    stem, ext = os.path.splitext(base)
    return stem, ext.lower()


def _detect_code_pill_icon(text: str, href: str = "") -> tuple[str, str] | None:
    """Return ``(nerd_glyph, hex_color)`` when a code pill or link refers to a code file."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if href:
        parsed = urllib.parse.urlparse(href)
        scheme = (parsed.scheme or "").lower()
        if scheme in ("", "file"):
            stem, ext = _extract_file_ext(href)
            if stem and ext in _EXT_NERD_ICONS:
                return _EXT_NERD_ICONS[ext]
            t_stem, t_ext = _extract_file_ext(cleaned)
            if t_stem and t_ext in _EXT_NERD_ICONS:
                return _EXT_NERD_ICONS[t_ext]
            if scheme == "file" and (parsed.path or "").endswith("/"):
                return ("\uf07b", "#79C0FF")
            if scheme == "file" and stem:
                return ("\uf15b", "#8B949E")
        return None

    # Standalone inline code: only attach an icon when it is a clean file path
    # with a known source/config/doc extension (never for bare ".md" or flags).
    if " " in cleaned or cleaned.startswith(("-", ".")):
        return None
    stem, ext = _extract_file_ext(cleaned)
    if stem and ext in _STANDALONE_ICON_EXTS:
        return _EXT_NERD_ICONS[ext]
    return None


def _decode_shields_part(part: str) -> str:
    unquoted = urllib.parse.unquote(part)
    unquoted = unquoted.replace("--", "\x00").replace("__", "\x01")
    unquoted = unquoted.replace("_", " ").replace("\x00", "-").replace("\x01", "_")
    return unquoted.strip()


def _format_shields_badge(src: str, alt: str) -> str | None:
    """Render ``https://img.shields.io/badge/<label>-<msg>-<color>`` as a 2-part pill."""
    if not src or "shields.io/badge/" not in src:
        return None
    try:
        tail = src.split("shields.io/badge/", 1)[1].split("?", 1)[0]
        if tail.lower().endswith(".svg") or tail.lower().endswith(".png"):
            tail = tail.rsplit(".", 1)[0]
        # Protect escaped double hyphens '--' before splitting on '-'
        protected = tail.replace("--", "\x00")
        segments = protected.split("-")
        if len(segments) >= 3:
            raw_label = segments[0].replace("\x00", "--")
            raw_color = segments[-1].replace("\x00", "").lower().lstrip("#")
            raw_msg = "-".join(segments[1:-1]).replace("\x00", "--")
            label = html.escape(_decode_shields_part(raw_label))
            msg = html.escape(_decode_shields_part(raw_msg))
            right_bg = _SHIELDS_COLOR_MAP.get(raw_color)
            if right_bg is None:
                if re.fullmatch(r"[0-9a-f]{6}", raw_color):
                    right_bg = f"#{raw_color.upper()}"
                else:
                    right_bg = "#2F81F7"
            return (
                f'<span font_family="monospace" size="90%" weight="bold" '
                f'background="#30363D" foreground="#F0F6FC">\u00a0{label}\u00a0</span>'
                f'<span font_family="monospace" size="90%" weight="bold" '
                f'background="{right_bg}" foreground="#FFFFFF">\u00a0{msg}\u00a0</span>'
            )
    except Exception:
        logger.debug("Could not parse shields.io badge %s", src, exc_info=True)
    if alt:
        escaped_alt = html.escape(alt)
        return (
            f'<span font_family="monospace" size="90%" weight="bold" '
            f'background="#30363D" foreground="#F0F6FC">\u00a0{escaped_alt}\u00a0</span>'
        )
    return None


def _render_code_pill(text: str, pill_bg: str, pill_fg: str, icon: tuple[str, str] | None) -> str:
    escaped = html.escape(text)
    if icon is not None:
        glyph, icon_color = icon
        return (
            f'<span font_family="{_ICON_FONT_FAMILY}" size="94%" '
            f'background="{pill_bg}" foreground="{pill_fg}">'
            f'\u00a0<span foreground="{icon_color}">{glyph}</span> {escaped}\u00a0</span>'
        )
    return (
        f'<span font_family="monospace" size="94%" '
        f'background="{pill_bg}" foreground="{pill_fg}">\u00a0{escaped}\u00a0</span>'
    )


def inline_tokens_to_pango_markup(children) -> str:
    """Convert markdown-it inline tokens into Antigravity-style Pango markup."""
    if not children:
        return ""
    dark = is_dark_theme()
    pill_bg = "#1E222A" if dark else "#EEF2F7"
    pill_fg = "#79C0FF" if dark else "#1F57C3"
    accent = "#79C0FF" if dark else "#1F57C3"
    link_stack: list[str] = []
    last_was_badge = False
    parts = []
    n = len(children)
    for idx, tok in enumerate(children):
        ttype = tok.type
        if ttype == "text":
            current_href = link_stack[-1] if link_stack else ""
            # If a local file:// link was written as [label](file:///path.rs)
            # without backticks, still render it as an Antigravity file pill.
            if (
                current_href
                and tok.content.strip()
                and urllib.parse.urlparse(current_href).scheme.lower() in ("", "file")
                and _detect_code_pill_icon(tok.content, current_href) is not None
            ):
                icon = _detect_code_pill_icon(tok.content, current_href)
                parts.append(_render_code_pill(tok.content.strip(), pill_bg, pill_fg, icon))
            else:
                parts.append(html.escape(tok.content))
            last_was_badge = False
        elif ttype == "code_inline":
            current_href = link_stack[-1] if link_stack else ""
            icon = _detect_code_pill_icon(tok.content, current_href)
            parts.append(_render_code_pill(tok.content, pill_bg, pill_fg, icon))
            last_was_badge = False
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
            raw_href = ""
            if tok.attrs and "href" in tok.attrs:
                raw_href = str(tok.attrs["href"])
            escaped_href = html.escape(raw_href, quote=True)
            link_stack.append(raw_href)
            parts.append(f'<a href="{escaped_href}"><span underline="none" foreground="{accent}">')
        elif ttype == "link_close":
            if link_stack:
                link_stack.pop()
            parts.append("</span></a>")
        elif ttype == "softbreak":
            # Keep consecutive shields.io badges on the same horizontal row.
            next_is_badge = False
            for look_idx in range(idx + 1, min(n, idx + 3)):
                ltok = children[look_idx]
                if ltok.type == "image":
                    lsrc = ltok.attrs.get("src", "") if ltok.attrs else ""
                    if "shields.io/badge/" in lsrc:
                        next_is_badge = True
                    break
            parts.append("  " if (last_was_badge and next_is_badge) else "\n")
        elif ttype == "hardbreak":
            parts.append("\n")
            last_was_badge = False
        elif ttype == "image":
            src = tok.attrs.get("src", "") if tok.attrs else ""
            alt = tok.content or ""
            badge_markup = _format_shields_badge(src, alt)
            if badge_markup is not None:
                parts.append(badge_markup)
                last_was_badge = True
            elif src and not src.startswith(("http://", "https://", "data:")):
                # Local images are already rendered as Gtk.Picture widgets above
                # the paragraph; do not emit ugly "[image] ..." fallback text.
                last_was_badge = False
            else:
                escaped_alt = html.escape(alt or _("image"))
                parts.append(f'<span foreground="{accent}">[{escaped_alt}]</span>')
                last_was_badge = False
        elif ttype == "html_inline":
            raw_tag = tok.content.strip().lower()
            if raw_tag in ("<br>", "<br/>", "<br />"):
                parts.append("\n")
            elif raw_tag == "<kbd>":
                parts.append(
                    f'<span font_family="monospace" size="94%" background="{pill_bg}" foreground="{pill_fg}">\u00a0'
                )
            elif raw_tag == "</kbd>":
                parts.append("\u00a0</span>")
            else:
                parts.append(html.escape(tok.content))
            last_was_badge = False
    return "".join(parts)


def _read_markdown_file(file_path: str, size: int, cancellable=None):
    """Read at most the documented Markdown cap and decode it.

    A file above ``MARKDOWN_READ_LIMIT`` is cut at the cap with a translated
    truncation note. ``cancellable`` is checked between chunks. Returns
    ``None`` when cancelled.
    """
    truncated = size > MARKDOWN_READ_LIMIT
    chunks = []
    remaining = MARKDOWN_READ_LIMIT
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
        content += _("\n\n... [Truncated preview: file is larger than 2 MB] ...")
    return content


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
        self.search_state_callback = None
        self._status_callback = None
        self._ready_callback = None
        self._is_mermaid = False
        self._size_bytes = 0
        self._line_count = 1
        self._word_count = 0
        self._mermaid_cards = []
        self._copy_timeout_ids = set()

        # Rendered blocks and their source line ranges. Clicking a block marks
        # it; Shift+click extends; Ctrl+click toggles non-contiguous blocks.
        self._md_blocks = []
        self._md_selected_indices: set[int] = set()
        self._md_quote_first = None
        self._md_quote_last = None
        self._md_quote_start = 0
        self._md_quote_end = 0
        self._md_quote_source = ""
        self._md_block_click_handled = False
        self._quote_bar = None
        self._md_search = None
        self._pending_nav_state = None
        self._pending_line_range = None
        self._scroll_restore_id = None

        # Every initial load gets a generation; results from an older
        # generation are discarded. Reads above the threshold run on a worker.
        self._load_generation = 0
        self._load_cancellable = None
        self._load_thread = None

        # Controls live in the window header now. They are kept parentless so
        # the window can pack them; no per-viewer toolbar row is appended.
        self.toolbar = None
        self.lbl_badge = Gtk.Label(label=_("PREVIEW"))
        self.lbl_badge.add_css_class("code-lang-badge")

        self.lbl_meta = Gtk.Label(label="")
        self.lbl_meta.add_css_class("code-meta-label")
        self.lbl_meta.set_halign(Gtk.Align.START)
        self.lbl_meta.set_hexpand(True)

        # Mode switch buttons: Preview (default) vs Raw Code
        self.mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.mode_box.add_css_class("linked")
        self.btn_mode_preview = Gtk.ToggleButton(label=_("Preview"))
        self.btn_mode_preview.add_css_class("code-btn-small")
        self.btn_mode_preview.set_tooltip_text(_("Show rendered preview"))
        self.btn_mode_preview.set_active(True)

        self.btn_mode_raw = Gtk.ToggleButton(label=_("Raw Code"))
        self.btn_mode_raw.add_css_class("code-btn-small")
        self.btn_mode_raw.set_tooltip_text(_("Show raw source"))
        self.btn_mode_raw.set_group(self.btn_mode_preview)

        self.btn_mode_preview.connect("toggled", self.on_mode_toggled)
        self.mode_box.append(self.btn_mode_preview)
        self.mode_box.append(self.btn_mode_raw)

        # Copy button
        self.btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        self.btn_copy.add_css_class("code-btn-small")
        self.btn_copy.set_tooltip_text(_("Copy source"))
        self.btn_copy.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Copy source")]
        )
        self.btn_copy.connect("clicked", self.on_copy_clicked)

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

        self.doc_clamp = Adw.Clamp()
        # Wide enough for five-column tables to stay readable; prose still
        # reads well because paragraphs wrap on their own.
        self.doc_clamp.set_maximum_size(980)
        self.doc_clamp.set_tightening_threshold(560)
        self.doc_clamp.set_child(self.doc_box)
        self.outer_box.append(self.doc_clamp)

        bg_click = Gtk.GestureClick.new()
        bg_click.set_button(Gdk.BUTTON_PRIMARY)
        bg_click.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        bg_click.connect("released", self._on_background_released)
        self.outer_box.add_controller(bg_click)

        self.preview_scroll.set_child(self.outer_box)

        self.preview_overlay = Gtk.Overlay()
        self.preview_overlay.set_vexpand(True)
        self.preview_overlay.set_child(self.preview_scroll)
        self._quote_bar = QuoteBar(self._on_quote_copy)
        self.preview_overlay.add_overlay(self._quote_bar)
        self.stack.add_named(self.preview_overlay, "preview")

        # Raw Code Page container (lazily populated when user clicks Raw Code)
        self.raw_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_named(self.raw_container, "raw")

        self.load_file()

    def load_file(self):
        """Start the initial load, synchronously for small files and on a worker above 1 MB."""
        self._load_generation += 1
        generation = self._load_generation
        self._cancel_pending_load()
        cancellable = Gio.Cancellable()
        self._load_cancellable = cancellable

        try:
            size = os.path.getsize(self.file_path)
            if size > MARKDOWN_ASYNC_READ_THRESHOLD:
                self._load_thread = threading.Thread(
                    target=self._worker_load_file,
                    args=(size, generation, cancellable),
                    daemon=True,
                )
                self._load_thread.start()
                return

            content = _read_markdown_file(self.file_path, size, cancellable)
        except Exception as e:
            self._show_load_error(e)
            return

        if content is not None:
            self._apply_loaded_content(content, size, generation)

    def _worker_load_file(self, size: int, generation: int, cancellable) -> None:
        try:
            content = _read_markdown_file(self.file_path, size, cancellable)
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
        err = Gtk.Label(
            label=_("Could not render preview:\n{error}").format(error=error)
        )
        self.doc_box.append(err)

    def _apply_loaded_content(self, content: str, size: int, generation: int) -> None:
        if generation != self._load_generation:
            return
        self.raw_content = content

        try:
            ext = os.path.splitext(self.file_path)[1].lower()
            is_standalone_mermaid = ext in (".mmd", ".mermaid") or is_mermaid_content(content)
            self._is_mermaid = is_standalone_mermaid
            self._size_bytes = size
            self._line_count = content.count("\n") + 1
            self._word_count = len(re.findall(r"\S+", content))

            if is_standalone_mermaid:
                self.lbl_badge.set_text(_("MERMAID"))
                lines_text = ngettext(
                    "{count} line", "{count} lines", self._line_count
                ).format(count=f"{self._line_count:,}")
                self.lbl_meta.set_text(
                    _("{diagram}  •  {lines}  •  {size}").format(
                        diagram=detect_mermaid_diagram_type(content),
                        lines=lines_text,
                        size=format_size(size),
                    )
                )
                card = MermaidDiagramCard(content)
                self._mermaid_cards.append(card)
                self.doc_box.append(card)
            else:
                self.lbl_badge.set_text(_("MARKDOWN"))
                self._render_markdown(content, size)

            self.stack.set_visible_child_name("preview")

            # If the user opened Raw while the background read was running,
            # give the existing raw viewer the newly loaded source.
            if self.raw_viewer_loaded and self.raw_viewer is not None:
                self.raw_viewer.raw_content = content
                self.raw_viewer.load_text()

            if self._pending_nav_state is not None:
                state = self._pending_nav_state
                self._pending_nav_state = None
                self.restore_navigation_state(state)
            elif self._pending_line_range is not None:
                first_line, last_line = self._pending_line_range
                self._pending_line_range = None
                self.focus_line_range(first_line, last_line)

        except Exception as e:
            err = Gtk.Label(
                label=_("Could not render preview:\n{error}").format(error=e)
            )
            self.doc_box.append(err)

        self._notify_status_changed()
        self._notify_ready()

    def _cancel_scroll_restore(self) -> None:
        if self._scroll_restore_id is not None:
            GLib.source_remove(self._scroll_restore_id)
            self._scroll_restore_id = None

    def get_navigation_state(self) -> dict:
        """Capture the current mode, scroll offset, and selection for Back history."""
        mode = self.stack.get_visible_child_name() or "preview"
        vadj = self.preview_scroll.get_vadjustment()
        scroll_y = float(vadj.get_value()) if vadj is not None else 0.0
        raw_state = (
            self.raw_viewer.get_navigation_state()
            if (self.raw_viewer is not None and hasattr(self.raw_viewer, "get_navigation_state"))
            else None
        )
        return {
            "mode": mode,
            "scroll_y": scroll_y,
            "selected_indices": sorted(self._md_selected_indices),
            "raw_state": raw_state,
        }

    def restore_navigation_state(self, state: dict | None) -> None:
        """Restore mode and scroll position when returning via Back."""
        if not state:
            return
        if not self.raw_content:
            self._pending_nav_state = dict(state)
            return

        mode = state.get("mode", "preview")
        if mode == "raw":
            self.btn_mode_raw.set_active(True)
            self._ensure_raw_viewer()
            self.stack.set_visible_child_name("raw")
            raw_state = state.get("raw_state")
            if raw_state and self.raw_viewer is not None:
                self.raw_viewer.restore_navigation_state(raw_state)
            return

        self.btn_mode_preview.set_active(True)
        self.stack.set_visible_child_name("preview")

        selected = state.get("selected_indices") or []
        if selected:
            self._md_selected_indices = {
                int(i) for i in selected if 0 <= int(i) < len(self._md_blocks)
            }
            if self._md_selected_indices:
                self._md_quote_first = min(self._md_selected_indices)
                self._md_quote_last = max(self._md_selected_indices)
                self._apply_md_quote()

        target_y = float(state.get("scroll_y") or 0.0)
        if target_y <= 0.0:
            return
        self._cancel_scroll_restore()
        attempts = [0]

        def _try_restore():
            attempts[0] += 1
            vadj = self.preview_scroll.get_vadjustment()
            if vadj is None:
                self._scroll_restore_id = None
                return False
            max_scroll = max(0.0, vadj.get_upper() - vadj.get_page_size())
            if max_scroll >= target_y - 2.0 or attempts[0] >= 16:
                vadj.set_value(min(target_y, max_scroll))
                self._scroll_restore_id = None
                return False
            return True

        self._scroll_restore_id = GLib.timeout_add(25, _try_restore)

    def focus_line_range(self, first_line: int, last_line: int | None = None) -> None:
        """Scroll to and highlight the rendered Markdown block covering ``first_line``."""
        lo = max(1, int(first_line))
        hi = max(lo, int(last_line or first_line))
        if not self.raw_content:
            self._pending_line_range = (lo, hi)
            return
        if lo == 1 and hi >= max(1, self._line_count - 1):
            return
        target_idx = None
        for idx, (_widget, start_0, end_0) in enumerate(self._md_blocks):
            if start_0 + 1 <= hi and end_0 >= lo:
                target_idx = idx
                break
        if target_idx is None:
            return
        self._md_selected_indices = {target_idx}
        self._md_quote_first = target_idx
        self._md_quote_last = target_idx
        self._apply_md_quote()
        target_widget = self._md_blocks[target_idx][0]
        self._cancel_scroll_restore()
        attempts = [0]

        def _scroll_to_widget():
            attempts[0] += 1
            coords = target_widget.translate_coordinates(self.doc_box, 0, 0)
            vadj = self.preview_scroll.get_vadjustment()
            if coords is not None and vadj is not None and vadj.get_upper() > vadj.get_page_size():
                y_pos = max(0.0, float(coords[1]) - 36.0)
                max_scroll = max(0.0, vadj.get_upper() - vadj.get_page_size())
                vadj.set_value(min(y_pos, max_scroll))
                self._scroll_restore_id = None
                return False
            if attempts[0] >= 14:
                self._scroll_restore_id = None
                return False
            return True

        self._scroll_restore_id = GLib.timeout_add(25, _scroll_to_widget)

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logging.getLogger(__name__).exception("Markdown status callback failed")

    # ------------------------------------------------------- line-range quotes

    @staticmethod
    def _token_line_map(token) -> tuple[int, int]:
        """Return a markdown-it token's 0-based, end-exclusive source range."""
        line_map = getattr(token, "map", None)
        if not line_map or len(line_map) != 2:
            return 0, 0
        try:
            return int(line_map[0]), int(line_map[1])
        except (TypeError, ValueError):
            return 0, 0

    def _reset_md_quote(self) -> None:
        self._clear_md_quote()
        self._md_blocks = []

    def _clear_md_quote(self) -> None:
        for widget, _start, _end in self._md_blocks:
            widget.remove_css_class("md-quote-active")
            widget.remove_css_class("md-quote-hover")
        self._md_selected_indices.clear()
        self._md_quote_first = None
        self._md_quote_last = None
        self._md_quote_start = 0
        self._md_quote_end = 0
        if self._quote_bar is not None:
            self._quote_bar.hide_bar()

    def _on_background_released(self, gesture, n_press: int, x: float, y: float) -> None:
        """Dismiss the active quote selection when clicking outside any block."""
        if self._md_block_click_handled:
            self._md_block_click_handled = False
            return
        if self.has_line_selection():
            self._clear_md_quote()

    def _register_md_block(self, widget, start_line: int, end_line: int) -> None:
        """Register a rendered widget or list row for hover and quote selection."""
        if end_line <= start_line:
            return
        index = len(self._md_blocks)
        try:
            pointer = Gdk.Cursor.new_from_name("pointer")
            if pointer is not None:
                widget.set_cursor(pointer)
        except Exception:
            pass

        gesture = Gtk.GestureClick.new()
        gesture.set_button(Gdk.BUTTON_PRIMARY)
        gesture.connect("pressed", self._on_md_block_pressed, index)
        widget.add_controller(gesture)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("enter", lambda *_args, w=widget: w.add_css_class("md-quote-hover"))
        motion.connect("leave", lambda *_args, w=widget: w.remove_css_class("md-quote-hover"))
        widget.add_controller(motion)

        self._md_blocks.append((widget, start_line, end_line))

    def _append_md_block(self, widget, start_line: int, end_line: int) -> None:
        """Append a rendered block and remember its source line range."""
        self._register_md_block(widget, start_line, end_line)
        self.doc_box.append(widget)

    def _on_md_block_pressed(self, gesture, n_press: int, x: float, y: float, index: int) -> None:
        self._md_block_click_handled = True
        try:
            state = gesture.get_current_event_state()
            if isinstance(state, tuple):
                state = state[-1]
            shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
            ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        except Exception:
            shift = False
            ctrl = False

        if ctrl:
            if index in self._md_selected_indices:
                self._md_selected_indices.remove(index)
            else:
                self._md_selected_indices.add(index)
                self._md_quote_first = index
                self._md_quote_last = index
            if not self._md_selected_indices:
                self._clear_md_quote()
                return
        elif shift and self._md_quote_first is not None:
            self._md_quote_last = index
            low = max(0, min(self._md_quote_first, self._md_quote_last))
            high = min(
                len(self._md_blocks) - 1,
                max(self._md_quote_first, self._md_quote_last),
            )
            self._md_selected_indices = set(range(low, high + 1))
        else:
            if self._md_selected_indices == {index}:
                self._clear_md_quote()
                return
            self._md_quote_first = index
            self._md_quote_last = index
            self._md_selected_indices = {index}
        self._apply_md_quote()

    def _merged_selected_ranges(self) -> list[tuple[int, int]]:
        """Return merged 0-based ``(start_line, end_line)`` ranges for selected blocks."""
        if not self._md_blocks:
            return []
        if not self._md_selected_indices and self._md_quote_first is not None:
            low = max(0, min(self._md_quote_first, self._md_quote_last or self._md_quote_first))
            high = min(
                len(self._md_blocks) - 1,
                max(self._md_quote_first, self._md_quote_last or self._md_quote_first),
            )
            indices = sorted(range(low, high + 1))
        else:
            indices = sorted(
                i for i in self._md_selected_indices if 0 <= i < len(self._md_blocks)
            )
        if not indices:
            return []

        raw_ranges = sorted(
            (self._md_blocks[i][1], self._md_blocks[i][2])
            for i in indices
            if self._md_blocks[i][2] > self._md_blocks[i][1]
        )
        if not raw_ranges:
            return []

        merged: list[tuple[int, int]] = [raw_ranges[0]]
        for start, end in raw_ranges[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))
        return merged

    def _apply_md_quote(self) -> None:
        merged = self._merged_selected_ranges()
        if not merged:
            if self._quote_bar is not None:
                self._quote_bar.hide_bar()
            return

        active_set = set(self._md_selected_indices)
        if not active_set and self._md_quote_first is not None:
            low = max(0, min(self._md_quote_first, self._md_quote_last or self._md_quote_first))
            high = min(
                len(self._md_blocks) - 1,
                max(self._md_quote_first, self._md_quote_last or self._md_quote_first),
            )
            active_set = set(range(low, high + 1))

        for index, (widget, _start, _end) in enumerate(self._md_blocks):
            if index in active_set:
                widget.add_css_class("md-quote-active")
            else:
                widget.remove_css_class("md-quote-active")

        self._md_quote_start = merged[0][0]
        self._md_quote_end = merged[-1][1]
        display_ranges = [(start + 1, end) for start, end in merged]
        if hasattr(self._quote_bar, "set_ranges"):
            self._quote_bar.set_ranges(display_ranges)
        else:
            self._quote_bar.set_lines(self._md_quote_start + 1, self._md_quote_end)

    def _md_quote_segments(self) -> list[tuple[int, int, str]]:
        """Return ``[(first_line, last_line, text), ...]`` 1-based for selected blocks."""
        merged = self._merged_selected_ranges()
        if not merged:
            return []
        lines = self._md_quote_source.splitlines()
        segments: list[tuple[int, int, str]] = []
        for start, end in merged:
            first = max(0, min(start, len(lines)))
            last = max(first, min(end, len(lines)))
            if last <= first:
                continue
            text = "\n".join(lines[first:last])
            if text:
                segments.append((first + 1, last, text))
        return segments

    def _md_quote_text(self):
        """Return ``(first_line, last_line, text)`` 1-based, or ``None``."""
        segments = self._md_quote_segments()
        if not segments:
            return None
        return (
            segments[0][0],
            segments[-1][1],
            "\n\n".join(seg[2] for seg in segments),
        )

    def _on_quote_copy(self, reference: bool) -> bool:
        return self.copy_selected_lines(reference)

    def copy_selected_lines(self, reference: bool = True) -> bool:
        """Copy the selected rendered blocks, or the raw selection in raw mode."""
        if self.stack.get_visible_child_name() == "raw":
            if self.raw_viewer is not None:
                return bool(self.raw_viewer.copy_selected_lines(reference))
            return False

        segments = self._md_quote_segments()
        if not segments:
            return False
        if reference:
            payload = "\n".join(
                format_line_reference(self.file_path, first_line, last_line)
                for first_line, last_line, _text in segments
            )
        else:
            payload = "\n\n".join(text for _first, _last, text in segments)

        display = Gdk.Display.get_default()
        if display is None:
            return False
        display.get_clipboard().set(payload)
        if self._quote_bar is not None:
            self._quote_bar.flash(reference)
        return True

    def has_line_selection(self) -> bool:
        if self.stack.get_visible_child_name() == "raw" and self.raw_viewer is not None:
            getter = getattr(self.raw_viewer, "has_line_selection", None)
            return bool(getter()) if callable(getter) else False
        return bool(self._md_selected_indices) or self._md_quote_first is not None

    def clear_line_selection(self) -> None:
        if self.stack.get_visible_child_name() == "raw" and self.raw_viewer is not None:
            self.raw_viewer.clear_line_selection()
            return
        self._clear_md_quote()

    def _render_markdown(self, content: str, size: int):
        # A reload invalidates every stored match, including its widgets.
        if self._md_search is not None:
            self._md_search.reset()
        self._md_quote_source = content
        self._reset_md_quote()

        if not HAS_MARKDOWN_IT:
            lbl = Gtk.Label(label=content)
            lbl.set_wrap(True)
            lbl.set_selectable(True)
            self.doc_box.append(lbl)
            return

        md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
        md.validateLink = _validate_markdown_link
        tokens = md.parse(content)

        mermaid_count = 0
        code_count = 0
        heading_count = 0
        center_align = False

        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]
            ttype = tok.type

            # 0. HTML Blocks (<div align="center">, <img src="...">, </div>)
            if ttype == "html_block":
                raw_html = tok.content or ""
                lower_html = raw_html.lower()
                if "<div" in lower_html and (
                    'align="center"' in lower_html or "align='center'" in lower_html
                ):
                    center_align = True
                for img_match in re.finditer(r"<img\b([^>]*)/?>", raw_html, re.IGNORECASE):
                    attrs_str = img_match.group(1)
                    src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
                    w_m = re.search(r'\bwidth=["\']?(\d+)["\']?', attrs_str, re.IGNORECASE)
                    h_m = re.search(r'\bheight=["\']?(\d+)["\']?', attrs_str, re.IGNORECASE)
                    if src_m:
                        self._try_append_local_image(
                            src_m.group(1),
                            width=int(w_m.group(1)) if w_m else None,
                            height=int(h_m.group(1)) if h_m else None,
                            centered=center_align,
                        )
                if "</div>" in lower_html:
                    center_align = False
                i += 1
                continue

            # 1. Headings
            if ttype == "heading_open":
                level = tok.tag  # h1..h6
                heading_count += 1
                inline_tok = tokens[i + 1] if (i + 1 < n and tokens[i + 1].type == "inline") else None
                markup = inline_tokens_to_pango_markup(inline_tok.children if inline_tok else [])
                lbl = self._create_markup_label(markup, css_class=f"md-{level}")
                lbl.set_margin_top(10 if level in ("h1", "h2") else 6)
                if center_align:
                    lbl.set_halign(Gtk.Align.CENTER)
                    lbl.set_xalign(0.5)
                    lbl.set_justify(Gtk.Justification.CENTER)

                block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                block.append(lbl)
                if level in ("h1", "h2") and not center_align:
                    rule = Gtk.Box()
                    rule.add_css_class("md-heading-rule")
                    rule.set_margin_bottom(4)
                    block.append(rule)
                self._append_md_block(block, *self._token_line_map(tok))

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
                        self._try_append_local_image(src, centered=center_align)

                    markup = inline_tokens_to_pango_markup(inline_tok.children)
                    if markup.strip():
                        lbl = self._create_markup_label(markup, css_class="md-paragraph")
                        if center_align:
                            lbl.set_halign(Gtk.Align.CENTER)
                            lbl.set_xalign(0.5)
                            lbl.set_justify(Gtk.Justification.CENTER)
                        self._append_md_block(lbl, *self._token_line_map(tok))
                i += 3
                continue

            # 3. Fenced Code Blocks & Mermaid Blocks
            if ttype in ("fence", "code_block"):
                info = (tok.info or "").strip().split()[0].lower() if tok.info else ""
                code_text = tok.content.rstrip("\n")
                if info in ("mermaid", "mmd") or is_mermaid_content(code_text):
                    mermaid_count += 1
                    card = MermaidDiagramCard(code_text)
                    self._mermaid_cards.append(card)
                    self._append_md_block(card, *self._token_line_map(tok))
                else:
                    code_count += 1
                    card = self._create_code_block_card(code_text, info)
                    self._append_md_block(card, *self._token_line_map(tok))
                i += 1
                continue

            # 4. Blockquotes & GitHub Alerts ([!NOTE], [!TIP], [!IMPORTANT], [!WARNING], [!CAUTION])
            if ttype == "blockquote_open":
                end_i = self._find_matching_close(tokens, i, "blockquote_open", "blockquote_close")
                inner_tokens = tokens[i + 1 : end_i]
                block = self._build_blockquote_widget(inner_tokens)
                self._append_md_block(block, *self._token_line_map(tok))
                i = end_i + 1
                continue

            # 5. Bullet & Ordered Lists
            if ttype in ("bullet_list_open", "ordered_list_open"):
                close_type = "bullet_list_close" if ttype == "bullet_list_open" else "ordered_list_close"
                end_i = self._find_matching_close(tokens, i, ttype, close_type)
                is_ordered = ttype == "ordered_list_open"
                block = self._build_list_widget(tokens[i + 1 : end_i], is_ordered)
                self.doc_box.append(block)
                i = end_i + 1
                continue

            # 6. Tables
            if ttype == "table_open":
                end_i = self._find_matching_close(tokens, i, "table_open", "table_close")
                block = self._build_table_widget(tokens[i + 1 : end_i])
                self._append_md_block(block, *self._token_line_map(tok))
                i = end_i + 1
                continue

            # 7. Horizontal Rule
            if ttype == "hr":
                hr = Gtk.Box()
                hr.add_css_class("md-hr")
                self._append_md_block(hr, *self._token_line_map(tok))
                i += 1
                continue

            i += 1

        lines = content.count("\n") + 1
        meta_parts = [
            ngettext("{count} line", "{count} lines", lines).format(
                count=f"{lines:,}"
            )
        ]
        if heading_count:
            meta_parts.append(
                ngettext("{count} section", "{count} sections", heading_count).format(
                    count=heading_count
                )
            )
        if mermaid_count:
            meta_parts.append(
                ngettext(
                    "{count} Mermaid diagram",
                    "{count} Mermaid diagrams",
                    mermaid_count,
                ).format(count=mermaid_count)
            )
        if code_count:
            meta_parts.append(
                ngettext("{count} code block", "{count} code blocks", code_count).format(
                    count=code_count
                )
            )
        meta_parts.append(format_size(size))
        self._line_count = lines
        self._word_count = len(re.findall(r"\S+", content))
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
        # Keep selectable=False so clicking a block to quote/copy never places
        # a blinking text I-beam caret inside the paragraph; <a href> links
        # still fire activate-link normally.
        lbl.set_selectable(False)
        lbl.connect("activate-link", self._on_activate_link)
        try:
            lbl.set_markup(markup)
        except Exception:
            lbl.set_text(re.sub(r"<[^>]+>", "", markup))
        return lbl

    @staticmethod
    def _parse_line_fragment(fragment: str) -> tuple[int, int] | None:
        """Extract 1-based ``(first_line, last_line)`` from ``L10-L20`` or ``10-20``."""
        if not fragment:
            return None
        match = re.match(
            r"^[Ll]?(\d+)(?:[-:][Ll]?(\d+))?$",
            fragment.strip(),
        )
        if not match:
            return None
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        return max(1, min(first, last)), max(1, max(first, last))

    def _resolve_local_link_target(
        self, uri: str
    ) -> tuple[str, tuple[int, int] | None] | None:
        """Resolve a ``file://`` or relative link to ``(abs_path, line_range)``."""
        if not uri:
            return None
        parsed = urllib.parse.urlparse(uri)
        scheme = (parsed.scheme or "").lower()
        if scheme in ("http", "https", "mailto"):
            return None
        if scheme not in ("", "file"):
            return None

        raw_path = urllib.parse.unquote(parsed.path or "")
        fragment = parsed.fragment or ""
        line_range = self._parse_line_fragment(fragment)

        if not raw_path:
            return None
        if line_range is None and ":" in raw_path and not os.path.exists(raw_path):
            m = re.match(r"^(.*?):(\d+(?:-\d+)?)$", raw_path)
            if m:
                raw_path = m.group(1)
                line_range = self._parse_line_fragment(m.group(2))

        candidate = (
            raw_path
            if os.path.isabs(raw_path)
            else os.path.normpath(os.path.join(self.base_dir, raw_path))
        )
        if os.path.exists(candidate):
            return os.path.abspath(candidate), line_range
        return None

    def _on_activate_link(self, _label, uri: str) -> bool:
        """Preview linked local files inside Space Previewer when clicked."""
        self._md_block_click_handled = True
        resolved = self._resolve_local_link_target(uri)
        if resolved is None:
            return False
        target_path, line_range = resolved
        self._clear_md_quote()
        root = self.get_root()
        if root is not None and hasattr(root, "navigate_to_file"):
            root.navigate_to_file(target_path, line_range=line_range)
            return True
        return False

    def _create_code_block_card(self, code_text: str, lang_info: str) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("md-code-card")
        card.set_margin_top(4)
        card.set_margin_bottom(4)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("md-code-card-header")

        lbl_lang = Gtk.Label(label=(lang_info or "").upper() or _("CODE"))
        lbl_lang.add_css_class("code-lang-badge")
        header.append(lbl_lang)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        btn_copy = Gtk.Button(label=_("Copy"))
        btn_copy.add_css_class("code-btn-small")
        btn_copy.set_tooltip_text(_("Copy code block"))

        def _copy_block(_btn):
            display = Gdk.Display.get_default()
            if display:
                display.get_clipboard().set(code_text)
                self._flash_copied(btn_copy)

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

        if len(code_text.encode("utf-8", errors="replace")) > CODE_BLOCK_HIGHLIGHT_LIMIT:
            # Highlight only the prefix; keep the tail as plain text so
            # Pygments never lexes a very large code block.
            highlighted, remainder = split_at_byte_limit(
                code_text, CODE_BLOCK_HIGHLIGHT_LIMIT
            )
            detected_label = highlight_buffer_with_pygments(
                tv.get_buffer(),
                highlighted,
                lang_hint=lang_info or "text",
                max_bytes=CODE_BLOCK_HIGHLIGHT_LIMIT,
            )
            if remainder:
                tv.get_buffer().insert(
                    tv.get_buffer().get_end_iter(), remainder
                )
        else:
            detected_label = highlight_buffer_with_pygments(
                tv.get_buffer(), code_text, lang_hint=lang_info or "text"
            )
        lbl_lang.set_text(detected_label)
        card.append(tv)
        return card

    def _build_blockquote_widget(self, inner_tokens) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # A blockquote can hold tables, lists and code fences, not only text.
        # Collect the text first so the alert prefix is detected before the
        # nested blocks are appended in source order.
        inline_markups = []
        blocks = []
        index = 0
        total = len(inner_tokens)
        while index < total:
            token = inner_tokens[index]
            if token.type == "table_open":
                end_index = self._find_matching_close(
                    inner_tokens, index, "table_open", "table_close"
                )
                blocks.append(
                    self._build_table_widget(inner_tokens[index + 1 : end_index])
                )
                index = end_index + 1
                continue
            if token.type in ("bullet_list_open", "ordered_list_open"):
                close_type = (
                    "bullet_list_close"
                    if token.type == "bullet_list_open"
                    else "ordered_list_close"
                )
                end_index = self._find_matching_close(
                    inner_tokens, index, token.type, close_type
                )
                blocks.append(
                    self._build_list_widget(
                        inner_tokens[index + 1 : end_index],
                        token.type == "ordered_list_open",
                        1,
                    )
                )
                index = end_index + 1
                continue
            if token.type in ("fence", "code_block"):
                info = (
                    (token.info or "").strip().split()[0].lower()
                    if token.info
                    else ""
                )
                code_text = (token.content or "").rstrip("\n")
                if info in ("mermaid", "mmd") or is_mermaid_content(code_text):
                    card = MermaidDiagramCard(code_text)
                    self._mermaid_cards.append(card)
                    blocks.append(card)
                else:
                    blocks.append(self._create_code_block_card(code_text, info))
                index += 1
                continue
            if token.type == "inline" and token.children:
                inline_markups.append(inline_tokens_to_pango_markup(token.children))
            index += 1

        full_markup = "\n".join(inline_markups).strip()
        alert_colors = _alert_palette(is_dark_theme())
        alert_map = {
            "[!NOTE]": ("md-alert-note", alert_colors["note"], _("NOTE")),
            "[!TIP]": ("md-alert-tip", alert_colors["tip"], _("TIP")),
            "[!IMPORTANT]": (
                "md-alert-important",
                alert_colors["important"],
                _("IMPORTANT"),
            ),
            "[!WARNING]": (
                "md-alert-warning",
                alert_colors["warning"],
                _("WARNING"),
            ),
            "[!CAUTION]": (
                "md-alert-caution",
                alert_colors["caution"],
                _("CAUTION"),
            ),
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
        for block in blocks:
            box.append(block)
        return box

    def _build_list_widget(self, inner_tokens, is_ordered: bool, depth: int = 0) -> Gtk.Widget:
        list_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8 if depth == 0 else 6,
        )
        dark = is_dark_theme()
        accent = ACCENT_DARK if dark else ACCENT_LIGHT
        muted = "#8B949E" if dark else "#6B7280"
        green = "#7FB89A" if dark else "#3F7A5A"
        list_box.set_margin_start(8 if depth == 0 else 20)
        if depth > 0:
            list_box.set_margin_top(4)

        item_idx = 0
        i = 0
        n = len(inner_tokens)
        while i < n:
            if inner_tokens[i].type == "list_item_open":
                item_tok = inner_tokens[i]
                item_start, item_end = self._token_line_map(item_tok)
                end_i = self._find_matching_close(
                    inner_tokens, i, "list_item_open", "list_item_close"
                )
                item_idx += 1
                item_tokens = inner_tokens[i + 1 : end_i]

                item_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_valign(Gtk.Align.START)

                # Only the item's own text belongs on the bullet line; tables,
                # code fences and nested lists become blocks below it.
                direct_markups = []
                direct_starts = []
                direct_ends = []
                first_nested_start = None
                nested_widgets = []
                j = 0
                m = len(item_tokens)
                while j < m:
                    itok = item_tokens[j]
                    if itok.type in ("bullet_list_open", "ordered_list_open"):
                        ns, _ne = self._token_line_map(itok)
                        if ns > item_start and (
                            first_nested_start is None or ns < first_nested_start
                        ):
                            first_nested_start = ns
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
                    if itok.type == "table_open":
                        ns, ne = self._token_line_map(itok)
                        if ns > item_start and (
                            first_nested_start is None or ns < first_nested_start
                        ):
                            first_nested_start = ns
                        sub_end = self._find_matching_close(
                            item_tokens, j, "table_open", "table_close"
                        )
                        tbl_w = self._build_table_widget(item_tokens[j + 1 : sub_end])
                        self._register_md_block(tbl_w, ns, ne)
                        nested_widgets.append(tbl_w)
                        j = sub_end + 1
                        continue
                    if itok.type in ("fence", "code_block"):
                        ns, ne = self._token_line_map(itok)
                        if ns > item_start and (
                            first_nested_start is None or ns < first_nested_start
                        ):
                            first_nested_start = ns
                        info = (
                            (itok.info or "").strip().split()[0].lower()
                            if itok.info
                            else ""
                        )
                        code_text = (itok.content or "").rstrip("\n")
                        if info in ("mermaid", "mmd") or is_mermaid_content(code_text):
                            card = MermaidDiagramCard(code_text)
                            self._mermaid_cards.append(card)
                        else:
                            card = self._create_code_block_card(code_text, info)
                        self._register_md_block(card, ns, ne)
                        nested_widgets.append(card)
                        j += 1
                        continue
                    if itok.type == "blockquote_open":
                        ns, ne = self._token_line_map(itok)
                        if ns > item_start and (
                            first_nested_start is None or ns < first_nested_start
                        ):
                            first_nested_start = ns
                        sub_end = self._find_matching_close(
                            item_tokens, j, "blockquote_open", "blockquote_close"
                        )
                        bq_w = self._build_blockquote_widget(item_tokens[j + 1 : sub_end])
                        self._register_md_block(bq_w, ns, ne)
                        nested_widgets.append(bq_w)
                        j = sub_end + 1
                        continue
                    if itok.type == "hr":
                        rule = Gtk.Box()
                        rule.add_css_class("md-hr")
                        nested_widgets.append(rule)
                        j += 1
                        continue
                    if itok.type in ("paragraph_open", "inline"):
                        ps, pe = self._token_line_map(itok)
                        if pe > ps:
                            direct_starts.append(ps)
                            direct_ends.append(pe)
                    if itok.type == "inline" and itok.children:
                        direct_markups.append(inline_tokens_to_pango_markup(itok.children))
                    j += 1

                body_markup = "\n".join(direct_markups).strip()

                bullet_fg = "#C9D1D9" if dark else "#374151"
                bullet_markup = (
                    f'<span foreground="{bullet_fg}" weight="bold">{item_idx}.</span>'
                    if is_ordered
                    else f'<span foreground="{bullet_fg}" weight="bold">•</span>'
                )
                if body_markup.startswith("[x] ") or body_markup.startswith("[X] "):
                    bullet_markup = f'<span foreground="{green}" weight="bold">[x]</span>'
                    body_markup = body_markup[4:]
                elif body_markup.startswith("[ ] "):
                    bullet_markup = f'<span foreground="{muted}" weight="bold">[ ]</span>'
                    body_markup = body_markup[4:]

                baseline_align = getattr(Gtk.Align, "BASELINE_FILL", Gtk.Align.BASELINE)
                row.set_baseline_position(Gtk.BaselinePosition.TOP)

                lbl_bullet = self._create_markup_label(
                    bullet_markup, css_class="md-paragraph", wrap=False
                )
                lbl_bullet.set_valign(baseline_align)
                lbl_bullet.set_xalign(1.0)
                row.append(lbl_bullet)

                if body_markup:
                    lbl_body = self._create_markup_label(body_markup, css_class="md-paragraph")
                    lbl_body.set_hexpand(True)
                    lbl_body.set_valign(baseline_align)
                    row.append(lbl_body)

                row_start = min(direct_starts) if direct_starts else item_start
                row_end = max(direct_ends) if direct_ends else (
                    first_nested_start if first_nested_start is not None else item_end
                )
                if first_nested_start is not None and row_end > first_nested_start:
                    row_end = first_nested_start
                if row_end <= row_start and item_end > row_start:
                    row_end = min(item_end, row_start + 1)
                self._register_md_block(row, row_start, row_end)

                item_vbox.append(row)

                if nested_widgets:
                    indent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    indent.set_margin_start(24)
                    indent.set_margin_top(4)
                    for nested_widget in nested_widgets:
                        indent.append(nested_widget)
                    item_vbox.append(indent)

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
                    # Every cell wraps. A non-wrapping cell pins the table to
                    # the width of its longest line, which pushes the whole
                    # document past the reading column on long documents.
                    # WORD_CHAR is the fallback for long identifiers: without
                    # it a single unbreakable token sets the table minimum.
                    wrap=True,
                    wrap_mode=Pango.WrapMode.WORD_CHAR,
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

                # Give every column a readable floor. Long identifiers use
                # WORD_CHAR wrap so a single token cannot set the table width.
                if is_short_col:
                    width_chars = min(max(col_len, 8), 22)
                    lbl.set_width_chars(width_chars)
                    lbl.set_max_width_chars(width_chars)
                else:
                    lbl.set_width_chars(20)
                    lbl.set_max_width_chars(40)

                cell_box.append(lbl)
                grid.attach(cell_box, c_idx, r_idx, 1, 1)

        return grid

    def _try_append_local_image(
        self,
        src: str,
        width: int | None = None,
        height: int | None = None,
        centered: bool = False,
    ):
        if not src or src.startswith(("http://", "https://", "data:")):
            return
        candidate = src if os.path.isabs(src) else os.path.join(self.base_dir, src)
        if os.path.exists(candidate):
            try:
                if width and height:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        candidate, width, height, True
                    )
                else:
                    pb = GdkPixbuf.Pixbuf.new_from_file(candidate)
                pic = Gtk.Picture.new_for_pixbuf(pb)
                pic.set_can_shrink(True)
                pic.set_halign(Gtk.Align.CENTER if centered else Gtk.Align.START)
                target_h = height if height else min(pb.get_height(), 420)
                target_w = width if width else -1
                pic.set_size_request(target_w, target_h)
                self.doc_box.append(pic)
            except Exception:
                logger.debug("Could not embed image %s", candidate, exc_info=True)

    def _ensure_raw_viewer(self):
        if not self.raw_viewer_loaded:
            self.raw_viewer = TextViewer(
                self.file_path, raw_content=self.raw_content, show_toolbar=False
            )
            if self.search_state_callback is not None:
                self.raw_viewer.set_search_state_callback(self.search_state_callback)
            self.raw_container.append(self.raw_viewer)
            self.raw_viewer_loaded = True

    def on_mode_toggled(self, btn):
        was_open = self.is_search_open()
        query = ""
        if was_open:
            if self.stack.get_visible_child_name() == "raw" and self.raw_viewer is not None:
                query = self.raw_viewer.search_entry.get_text()
            elif self._md_search is not None:
                query = self._md_search.query()

        if self.btn_mode_preview.get_active():
            self.stack.set_visible_child_name("preview")
            if self.raw_viewer is not None and self.raw_viewer.is_search_open():
                self.raw_viewer.close_search()
            if was_open and query:
                self._ensure_markdown_search().open_with_query(query)
        else:
            self._clear_md_quote()
            self._ensure_raw_viewer()
            self.stack.set_visible_child_name("raw")
            if self._md_search is not None and self._md_search.is_open():
                self._md_search.close()
            if was_open:
                self.raw_viewer.set_search_query(query, open_bar=True)

        if was_open:
            # The window hosts one search bar at a time; re-sync so the new
            # mode's bar is the one in the overlay card.
            self._notify_search_state()

    def _flash_copied(self, btn):
        btn.set_label(_("Copied!"))
        holder = {}

        def reset():
            self._copy_timeout_ids.discard(holder["id"])
            btn.set_label(_("Copy"))
            return False

        holder["id"] = GLib.timeout_add(1300, reset)
        self._copy_timeout_ids.add(holder["id"])

    def on_copy_clicked(self, btn):
        display = Gdk.Display.get_default()
        if display and self.raw_content:
            display.get_clipboard().set(self.raw_content)
            self._flash_copied(btn)

    def toggle_search(self):
        """Search the rendered preview; Ctrl+F no longer jumps to Raw Code."""
        if self.stack.get_visible_child_name() == "raw" and self.raw_viewer:
            self.raw_viewer.toggle_search()
            return
        self._ensure_markdown_search().toggle()

    def close_search(self):
        if self.stack.get_visible_child_name() == "raw" and self.raw_viewer:
            self.raw_viewer.close_search()
            return
        if self._md_search is not None:
            self._md_search.close()

    def is_search_open(self) -> bool:
        if self.stack.get_visible_child_name() == "raw" and self.raw_viewer:
            return self.raw_viewer.is_search_open()
        return bool(self._md_search and self._md_search.is_open())

    def _ensure_markdown_search(self):
        if self._md_search is None:
            self._md_search = MarkdownSearch(self, is_dark_theme())
        return self._md_search

    def focus_preview(self):
        """Return focus to the preview column after closing search."""
        try:
            self.preview_scroll.grab_focus()
        except Exception:
            logger.debug("Could not focus the preview column", exc_info=True)

    def set_search_state_callback(self, callback) -> None:
        self.search_state_callback = callback
        if self.raw_viewer is not None:
            self.raw_viewer.set_search_state_callback(callback)

    def _notify_search_state(self) -> None:
        """Let the window show or hide the overlay that hosts the search bar."""
        callback = self.search_state_callback
        if callable(callback):
            try:
                callback(self.is_search_open())
            except Exception:
                logger.exception("Search state callback failed")

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

    def get_header_controls(self) -> list:
        """Return the linked Preview/Raw toggle and Copy, highest priority first."""
        return [self.mode_box, self.btn_copy]

    def get_status_items(self) -> list[tuple[str, str]]:
        return [
            (_("Size"), format_size(self._size_bytes)),
            (_("Words"), f"{self._word_count:,}"),
            (_("Encoding"), "UTF-8"),
        ]

    def get_search_widget(self):
        """Return the search bar for whichever mode is visible."""
        if self.stack.get_visible_child_name() == "raw":
            self._ensure_raw_viewer()
            return self.raw_viewer.get_search_widget() if self.raw_viewer else None
        return self._ensure_markdown_search().widget()

    def teardown(self) -> None:
        """Cancel the initial load, mermaid renders and timers owned here."""
        self._load_generation += 1
        self._cancel_pending_load()
        self._cancel_scroll_restore()
        self._load_thread = None
        self._status_callback = None
        if self._quote_bar is not None:
            self._quote_bar.teardown()
        for card in self._mermaid_cards:
            card.teardown()
        self._mermaid_cards.clear()
        if self.raw_viewer is not None:
            self.raw_viewer.teardown()
        for source_id in list(self._copy_timeout_ids):
            GLib.source_remove(source_id)
        self._copy_timeout_ids.clear()

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        lines = self.raw_content.count("\n") + 1 if self.raw_content else 20
        content_h = 160 + int(lines * 22)
        min_h = 420
        max_h = min(980, int(screen_h * 0.82))
        return target_w, max(min_h, min(max_h, content_h))
