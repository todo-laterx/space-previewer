import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from utils.formatters import format_size
from utils.i18n import _

logger = logging.getLogger(__name__)

# Untrusted input cap: reject images above 50 megapixels before any scaling.
MAX_IMAGE_PIXELS = 50_000_000
MIN_ZOOM = 0.1
MAX_ZOOM = 5.0
ZOOM_STEP = 1.15

# Only the root <svg> tag is needed to read the intrinsic size.
_SVG_HEAD_BYTES = 64 * 1024
_SVG_ROOT_RE = re.compile(r"<svg\b", re.IGNORECASE)
_SVG_ATTR_RE = re.compile(
    r"""([A-Za-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')"""
)
_SVG_LENGTH_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z%]*)\s*$"
)
_SVG_UNIT_SCALE = {
    "": 1.0,
    "px": 1.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "mm": 96.0 / 25.4,
    "cm": 96.0 / 2.54,
    "in": 96.0,
}


def _svg_length_px(value: str) -> float | None:
    """Convert an SVG length attribute to CSS pixels, or return None."""
    match = _SVG_LENGTH_RE.match(value or "")
    if match is None:
        return None
    unit = match.group(2).lower()
    if unit not in _SVG_UNIT_SCALE:
        return None
    return float(match.group(1)) * _SVG_UNIT_SCALE[unit]


def _parse_svg_size(file_path: str) -> tuple[int, int] | None:
    """Read the intrinsic SVG size without rasterising the document.

    Returns None when the file does not look like an SVG. Huge documents are
    rejected by the caller before Gtk.Picture or GdkPixbuf touch them.
    """
    try:
        with open(file_path, "rb") as handle:
            head = handle.read(_SVG_HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None

    if _SVG_ROOT_RE.search(head) is None:
        return None

    # Only the root <svg> tag carries the intrinsic size; nested elements may
    # have their own width/height attributes.
    root_match = _SVG_ROOT_RE.search(head)
    root_end = head.find(">", root_match.end())
    root_tag = head[root_match.start():]
    if root_end != -1:
        root_tag = head[root_match.start():root_end + 1]

    attributes: dict[str, str] = {}
    for match in _SVG_ATTR_RE.finditer(root_tag):
        name = match.group(1).lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        attributes.setdefault(name, value or "")

    width = _svg_length_px(attributes.get("width", ""))
    height = _svg_length_px(attributes.get("height", ""))

    viewbox_size = None
    viewbox = attributes.get("viewbox", "")
    if viewbox:
        parts = re.split(r"[\s,]+", viewbox.strip())
        if len(parts) == 4:
            try:
                vb_width = abs(float(parts[2]))
                vb_height = abs(float(parts[3]))
            except ValueError:
                vb_width = vb_height = 0.0
            if vb_width > 0 and vb_height > 0:
                viewbox_size = (vb_width, vb_height)

    if width is not None and height is not None and width > 0 and height > 0:
        size = (width, height)
    elif viewbox_size is not None:
        size = viewbox_size
    elif width is not None or height is not None:
        known_w = width if width is not None else height
        known_h = height if height is not None else known_w
        size = (known_w or 0.0, known_h or 0.0)
    else:
        # SVG defaults when no intrinsic size can be determined.
        size = (300.0, 150.0)

    return max(0, int(round(size[0]))), max(0, int(round(size[1])))


class ImageViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.zoom_factor = 1.0
        self.pixbuf_orig = None
        self._current_pixbuf = None
        self._image_size = (0, 0)
        self._animation = None
        self._animation_iter = None
        self._animation_timeout_id = None
        self._status_callback = None
        self._scroll_controller = None
        self._error_label = None

        try:
            self._file_size = os.path.getsize(file_path)
        except OSError:
            self._file_size = None

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_halign(Gtk.Align.CENTER)
        self.picture.set_valign(Gtk.Align.CENTER)

        # Center box
        self.center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.center_box.set_halign(Gtk.Align.CENTER)
        self.center_box.set_valign(Gtk.Align.CENTER)
        self.center_box.set_hexpand(True)
        self.center_box.set_vexpand(True)
        self.center_box.append(self.picture)

        self.scrolled.set_child(self.center_box)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_dims = Gtk.Label(label="")
        self.lbl_dims.add_css_class("dim-label")
        self.info_bar.append(self.lbl_dims)

        self.lbl_size = Gtk.Label(label="")
        self.lbl_size.add_css_class("dim-label")
        self.info_bar.append(self.lbl_size)

        self.append(self.info_bar)

        # Load image
        self.load_image()

        # Scroll controller for Ctrl+scroll zoom
        self._scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        # Capture first so Ctrl+scroll zooms before the ScrolledWindow pans.
        self._scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(self._scroll_controller)

    # ------------------------------------------------------------- loading

    def load_image(self) -> None:
        extension = os.path.splitext(self.file_path)[1].lower()
        if extension == ".svg":
            self._load_svg()
        else:
            self._load_raster()

    def _load_svg(self) -> None:
        svg_size = _parse_svg_size(self.file_path)
        if svg_size is None:
            self._show_error(
                _("Could not load image: {error}").format(
                    error=_("not a valid SVG document")
                )
            )
            return
        if svg_size[0] * svg_size[1] > MAX_IMAGE_PIXELS:
            self._show_error(self._too_large_message())
            return

        # Gtk.Picture renders SVG through librsvg without an intermediate
        # pixbuf, so it is preferred whenever this GTK version supports it.
        if hasattr(Gtk.Picture, "new_for_filename"):
            try:
                loader = Gtk.Picture.new_for_filename(
                    os.path.abspath(self.file_path)
                )
                paintable = loader.get_paintable() if loader is not None else None
                if paintable is not None:
                    width = paintable.get_intrinsic_width()
                    height = paintable.get_intrinsic_height()
                    if width <= 0 or height <= 0:
                        width, height = svg_size
                    if width * height > MAX_IMAGE_PIXELS:
                        self._show_error(self._too_large_message())
                        return
                    self.picture.set_paintable(paintable)
                    self._image_size = (width, height)
                    self.pixbuf_orig = None
                    self._current_pixbuf = None
                    self._update_info()
                    return
            except Exception as error:
                logger.warning("Gtk.Picture could not load SVG %s: %s", self.file_path, error)

        # Older GTK versions, or librsvg declined the document: try the
        # pixbuf loader. The parsed size is already known to be safe.
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.file_path)
        except Exception as error:
            logger.warning("Could not load SVG %s: %s", self.file_path, error)
            self._show_error(_("Could not load image: {error}").format(error=error))
            return
        self._set_static_pixbuf(pixbuf)
        self._update_info()

    def _load_raster(self) -> None:
        width = height = 0
        try:
            file_info = GdkPixbuf.Pixbuf.get_file_info(self.file_path)
        except Exception:
            file_info = None
        if file_info is not None:
            width, height = file_info[1], file_info[2]
            if width > 0 and height > 0 and width * height > MAX_IMAGE_PIXELS:
                self._show_error(self._too_large_message())
                return

        extension = os.path.splitext(self.file_path)[1].lower()
        if extension == ".gif":
            try:
                animation = GdkPixbuf.PixbufAnimation.new_from_file(self.file_path)
                anim_width = animation.get_width()
                anim_height = animation.get_height()
                if anim_width * anim_height > MAX_IMAGE_PIXELS:
                    self._show_error(self._too_large_message())
                    return
                if animation.is_static_image():
                    self._set_static_pixbuf(animation.get_static_image())
                else:
                    self._start_animation(animation)
                self._update_info()
                return
            except Exception as error:
                logger.warning("Could not read GIF animation %s: %s", self.file_path, error)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.file_path)
        except Exception as error:
            logger.warning("Could not load image %s: %s", self.file_path, error)
            self._show_error(_("Could not load image: {error}").format(error=error))
            return

        width = pixbuf.get_width()
        height = pixbuf.get_height()
        if width > 0 and height > 0 and width * height > MAX_IMAGE_PIXELS:
            self._show_error(self._too_large_message())
            return

        self._set_static_pixbuf(pixbuf)
        self._update_info()

    def _set_static_pixbuf(self, pixbuf) -> None:
        self.pixbuf_orig = pixbuf
        self._current_pixbuf = pixbuf
        self._image_size = (pixbuf.get_width(), pixbuf.get_height())
        self._render_current()

    def _start_animation(self, animation) -> None:
        self._animation = animation

        animations_enabled = True
        settings = Gtk.Settings.get_default()
        if settings is not None:
            try:
                animations_enabled = bool(
                    settings.get_property("gtk-enable-animations")
                )
            except Exception:
                animations_enabled = True

        if not animations_enabled:
            self._set_static_pixbuf(animation.get_static_image())
            self._animation = None
            return

        try:
            self._animation_iter = animation.get_iter(None)
            first_frame = self._animation_iter.get_pixbuf()
            if first_frame is None:
                first_frame = animation.get_static_image()
            delay = self._animation_iter.get_delay_time()
        except Exception as error:
            logger.warning("Could not start animation %s: %s", self.file_path, error)
            self._animation_iter = None
            self._animation = None
            self._set_static_pixbuf(animation.get_static_image())
            return

        self.pixbuf_orig = first_frame
        self._current_pixbuf = first_frame
        self._image_size = (
            first_frame.get_width() if first_frame is not None else animation.get_width(),
            first_frame.get_height() if first_frame is not None else animation.get_height(),
        )
        self._render_current()

        if delay is not None and delay >= 0:
            self._animation_timeout_id = GLib.timeout_add(
                max(1, delay), self._on_animation_tick
            )

    def _on_animation_tick(self) -> bool:
        """Advance an animated GIF frame and schedule the next one."""
        self._animation_timeout_id = None
        animation_iter = self._animation_iter
        if animation_iter is None:
            return False

        try:
            animation_iter.advance(None)
            pixbuf = animation_iter.get_pixbuf()
            if pixbuf is not None:
                self.pixbuf_orig = pixbuf
                self._current_pixbuf = pixbuf
                self._render_current()
            delay = animation_iter.get_delay_time()
        except Exception:
            logger.exception("Animated image frame failed for %s", self.file_path)
            self._animation_iter = None
            return False

        if delay is None or delay < 0:
            self._animation_iter = None
            return False

        self._animation_timeout_id = GLib.timeout_add(
            max(1, delay), self._on_animation_tick
        )
        return False

    # ------------------------------------------------------------- rendering

    def _render_current(self) -> None:
        pixbuf = self._current_pixbuf
        if pixbuf is None:
            return

        width = max(1, int(pixbuf.get_width() * self.zoom_factor))
        height = max(1, int(pixbuf.get_height() * self.zoom_factor))
        try:
            if width == pixbuf.get_width() and height == pixbuf.get_height():
                scaled = pixbuf
            else:
                scaled = pixbuf.scale_simple(
                    width, height, GdkPixbuf.InterpType.BILINEAR
                )
            if scaled is None:
                return
            self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(scaled))
        except Exception:
            logger.exception("Could not scale image %s", self.file_path)

    def _update_info(self, notify: bool = True) -> None:
        width, height = self._image_size
        if width > 0 and height > 0:
            if abs(self.zoom_factor - 1.0) > 1e-6:
                self.lbl_dims.set_text(
                    _("{width} × {height} px ({percent}%)").format(
                        width=width,
                        height=height,
                        percent=int(round(self.zoom_factor * 100)),
                    )
                )
            else:
                self.lbl_dims.set_text(
                    _("{width} × {height} px").format(width=width, height=height)
                )
        else:
            self.lbl_dims.set_text("")

        self.lbl_size.set_text(self._size_text())

        if notify:
            self._notify_status_changed()

    def _size_text(self) -> str:
        if self._file_size is None:
            return "—"
        return format_size(self._file_size)

    def _too_large_message(self) -> str:
        return _(
            "Image is too large to preview (limit: {limit} megapixels)."
        ).format(limit=MAX_IMAGE_PIXELS // 1_000_000)

    def _show_error(self, message: str) -> None:
        self._image_size = (0, 0)
        self.pixbuf_orig = None
        self._current_pixbuf = None
        if self.picture.get_parent() is self.center_box:
            self.center_box.remove(self.picture)
        if self._error_label is not None and self._error_label.get_parent() is self.center_box:
            self.center_box.remove(self._error_label)
        self._error_label = Gtk.Label(label=message)
        self._error_label.set_wrap(True)
        self._error_label.add_css_class("dim-label")
        self.center_box.append(self._error_label)
        self._update_info()

    # ------------------------------------------------------------- zoom

    def on_scroll(self, controller, dx, dy) -> bool:
        try:
            state = controller.get_current_event_state()
            if isinstance(state, tuple):
                # Older PyGObject exposed the gboolean/out-param pair.
                state = state[-1]
            ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        except Exception:
            ctrl_pressed = False

        # Only Ctrl+scroll zooms; plain scrolling pans the ScrolledWindow.
        if not ctrl_pressed:
            return False
        if self._current_pixbuf is None or dy == 0:
            return False

        if dy < 0:
            new_zoom = self.zoom_factor * ZOOM_STEP
        else:
            new_zoom = self.zoom_factor / ZOOM_STEP
        self.zoom_factor = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))

        self._render_current()
        self._update_info()
        return True

    # ------------------------------------------------------------- contract

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callable(callback):
            try:
                callback()
            except Exception:
                logger.exception("Image status callback failed")

    def get_status_items(self) -> list[tuple[str, str]]:
        width, height = self._image_size
        if width > 0 and height > 0:
            dimensions = _("{width} × {height} px").format(
                width=width, height=height
            )
        else:
            dimensions = _("Unknown")
        return [
            (_("Dimensions"), dimensions),
            (_("Size"), self._size_text()),
            (_("Zoom"), f"{int(round(self.zoom_factor * 100))}%"),
        ]

    def teardown(self) -> None:
        if self._animation_timeout_id is not None:
            GLib.source_remove(self._animation_timeout_id)
            self._animation_timeout_id = None
        self._animation_iter = None
        self._animation = None
        self._status_callback = None
        if self._scroll_controller is not None:
            try:
                self.remove_controller(self._scroll_controller)
            except Exception:
                logger.debug("Could not remove image scroll controller", exc_info=True)
            self._scroll_controller = None

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        orig_w, orig_h = self._image_size
        if orig_w <= 0 or orig_h <= 0:
            return 900, 650

        # UI chrome overhead: headerbar (48) + infobar (40) + margins (32) = 120px
        chrome_h = 120
        chrome_w = 60

        max_w = int(screen_w * 0.85)
        max_h = int(screen_h * 0.82)
        min_w = 540
        min_h = 380

        avail_w = max_w - chrome_w
        avail_h = max_h - chrome_h

        scale = min(avail_w / orig_w, avail_h / orig_h, 1.0)
        disp_w = max(min_w - chrome_w, int(orig_w * scale))
        disp_h = max(min_h - chrome_h, int(orig_h * scale))

        target_w = max(min_w, min(max_w, disp_w + chrome_w))
        target_h = max(min_h, min(max_h, disp_h + chrome_h))
        return target_w, target_h
