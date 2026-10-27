import logging
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib, Gtk

logger = logging.getLogger(__name__)

try:
    gi.require_version('Poppler', '0.18')
    from gi.repository import Poppler

    import cairo

    HAS_POPPLER = True
except Exception as error:
    HAS_POPPLER = False
    logger.debug("Poppler is not available: %s", error)

from utils.formatters import format_size
from utils.i18n import _

# Untrusted input cap: render at most this many pages of a PDF.
MAX_PAGES = 100

MIN_SCALE = 0.25
MAX_SCALE = 3.0
PAGE_SPACING = 16
PAGE_MARGIN = 16
CHROME_HEIGHT = 96
# Keep this many pages around the viewport in GPU memory.
CACHE_RADIUS = 2
# Never rasterise a single page above this many pixels.
MAX_PAGE_PIXELS = 40_000_000
SCROLL_ANIMATION_MS = 220

_CSS_INSTALLED = False

PDF_VIEWER_CSS = """
.pdf-page {
    background-color: transparent;
}
.pdf-truncated {
    font-size: 12px;
    margin: 8px 0 18px 0;
}
"""


def _ensure_css() -> None:
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(PDF_VIEWER_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_INSTALLED = True


class PDFViewer(Gtk.Box):
    """Continuous, lazily rendered PDF preview fitted to the window width."""

    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        _ensure_css()

        self.file_path = file_path
        self._status_callback = None
        self._ready_callback = None

        self._doc = None
        self._page_count = 0
        self._rendered_page_count = 0
        self._page_sizes: list[tuple[float, float]] = []
        self._page_offsets: list[int] = []
        self._page_widgets: list[Gtk.Picture] = []
        self._textures: dict[int, Gdk.Texture] = {}
        self._rendered: set[int] = set()
        self._render_queue: list[int] = []
        self._render_idle_id = 0
        self._scroll_anim_id = 0
        self._size_poll_id = 0
        self._fit_scale = 1.0
        self._last_view_width = 0
        self._last_current_page = -1
        self._tearing_down = False

        try:
            self._file_size = os.path.getsize(file_path)
        except OSError:
            self._file_size = None

        # Header page controls, packed by the window.
        self.btn_prev = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.btn_prev.set_tooltip_text(_("Previous page"))
        self.btn_prev.connect("clicked", lambda *_: self.previous_page())

        self.btn_next = Gtk.Button.new_from_icon_name("go-down-symbolic")
        self.btn_next.set_tooltip_text(_("Next page"))
        self.btn_next.connect("clicked", lambda *_: self.next_page())

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_kinetic_scrolling(True)
        self.scrolled.set_overlay_scrolling(True)
        self.scrolled.set_focusable(True)
        self.append(self.scrolled)

        self.pages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=PAGE_SPACING)
        self.pages_box.set_halign(Gtk.Align.CENTER)
        self.pages_box.set_valign(Gtk.Align.START)
        self.pages_box.set_margin_top(PAGE_MARGIN)
        self.pages_box.set_margin_bottom(PAGE_MARGIN)
        self.scrolled.set_child(self.pages_box)

        vadj = self.scrolled.get_vadjustment()
        if vadj is not None:
            vadj.connect("value-changed", lambda *_: self._on_scrolled())

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.scrolled.add_controller(key_controller)
        click = Gtk.GestureClick.new()
        click.connect("pressed", lambda *_: self.scrolled.grab_focus())
        self.scrolled.add_controller(click)

        if HAS_POPPLER:
            self._load_document()
            # The window registers its ready callback after construction; let
            # it re-measure once the document is in place.
            GLib.idle_add(self._ready_idle)
            GLib.idle_add(self._focus_scroll)
        else:
            self._show_message(_("Poppler library is not installed for PDF rendering."))

        # Refit the page scale when the window width changes. GTK4 has no
        # size-allocate signal, so a cheap poll keeps the page fitted.
        self._size_poll_id = GLib.timeout_add(200, self._poll_view_width)

    # ------------------------------------------------------------- loading

    def _load_document(self) -> bool:
        if self._tearing_down:
            return False
        try:
            uri = GLib.filename_to_uri(os.path.abspath(self.file_path), None)
            self._doc = Poppler.Document.new_from_file(uri, None)
            if self._doc is None:
                raise RuntimeError("Poppler returned no document")
        except Exception as error:
            logger.exception("Could not load PDF %s", self.file_path)
            self._show_message(
                _("Could not load PDF:\n{error}").format(error=error)
            )
            return False

        try:
            total = int(self._doc.get_n_pages())
        except Exception:
            total = 0
        self._page_count = total
        self._rendered_page_count = min(total, MAX_PAGES)

        for index in range(self._rendered_page_count):
            try:
                width, height = self._doc.get_page(index).get_size()
            except Exception:
                width, height = 595.0, 842.0
            self._page_sizes.append((max(1.0, float(width)), max(1.0, float(height))))

        if self._rendered_page_count == 0:
            self._show_message(_("The document has no pages."))
            return False

        for index in range(self._rendered_page_count):
            picture = Gtk.Picture()
            picture.set_can_shrink(True)
            picture.set_halign(Gtk.Align.CENTER)
            picture.set_valign(Gtk.Align.START)
            picture.add_css_class("pdf-page")
            self.pages_box.append(picture)
            self._page_widgets.append(picture)

        if total > MAX_PAGES:
            note = Gtk.Label(
                label=_("Showing the first {shown} of {total} pages.").format(
                    shown=MAX_PAGES, total=total
                )
            )
            note.add_css_class("dim-label")
            note.add_css_class("pdf-truncated")
            note.set_wrap(True)
            self.pages_box.append(note)

        self._apply_fit(preserve_page=0, animate=False)
        # Render the first page before presenting so the window opens on content.
        self._render_page(0)
        self._update_page_buttons()
        self._notify_status_changed()
        return False

    def _ready_idle(self) -> bool:
        self._notify_ready()
        return False

    def _focus_scroll(self) -> bool:
        if not self._tearing_down:
            try:
                self.scrolled.grab_focus()
            except Exception:
                logger.debug("Could not focus the PDF scroller", exc_info=True)
        return False

    def _show_message(self, message: str) -> None:
        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.add_css_class("dim-label")
        label.set_margin_top(24)
        label.set_margin_bottom(24)
        self.pages_box.append(label)
        self._notify_ready()

    # ------------------------------------------------------------- layout

    def _available_width(self) -> int:
        width = self.scrolled.get_width()
        if width <= 0:
            width = self.get_width()
        if width <= 0:
            width = 900
        return max(120, width - 2 * PAGE_MARGIN)

    def _fit_scale_for_width(self, width: int) -> float:
        widest = max((size[0] for size in self._page_sizes), default=595.0)
        return max(MIN_SCALE, min(MAX_SCALE, width / widest))

    def _poll_view_width(self) -> bool:
        if self._tearing_down or not self._page_sizes:
            return not self._tearing_down
        width = self.scrolled.get_width()
        if width <= 0:
            return True
        if self._last_view_width == 0:
            self._last_view_width = width
            self._apply_fit(preserve_page=self._current_page(), animate=False)
            return True
        if abs(width - self._last_view_width) >= 4:
            page = self._current_page()
            self._last_view_width = width
            self._apply_fit(preserve_page=page, animate=False)
        return True

    def _apply_fit(self, preserve_page: int = 0, animate: bool = False) -> None:
        if not self._page_sizes:
            return
        scale = self._fit_scale_for_width(self._available_width())
        self._fit_scale = scale

        offsets: list[int] = []
        y = PAGE_MARGIN
        for index, (page_w, page_h) in enumerate(self._page_sizes):
            width = max(1, int(round(page_w * scale)))
            height = max(1, int(round(page_h * scale)))
            self._page_widgets[index].set_size_request(width, height)
            offsets.append(y)
            y += height + PAGE_SPACING
        self._page_offsets = offsets

        self._clear_all_textures()
        self._last_current_page = -1
        self._update_visible_pages()
        if preserve_page is not None:
            GLib.timeout_add(30, self._restore_page_scroll, preserve_page, animate)

    def _restore_page_scroll(self, page: int, animate: bool) -> bool:
        if self._tearing_down:
            return False
        if 0 <= page < len(self._page_offsets):
            self._scroll_to_offset(self._page_offsets[page], animate=animate)
        return False

    # ------------------------------------------------------------- scrolling

    def _on_scrolled(self) -> None:
        # While a page jump animates, the viewport crosses many pages. Updating
        # on every frame would queue a render for each one; the animation end
        # does a single update at the destination.
        if self._scroll_anim_id:
            return
        self._update_visible_pages()

    def _current_page(self) -> int:
        if not self._page_offsets:
            return 0
        vadj = self.scrolled.get_vadjustment()
        top = vadj.get_value() if vadj else 0
        current = 0
        for index, offset in enumerate(self._page_offsets):
            if offset <= top + 4:
                current = index
            else:
                break
        return current

    def _visible_indices(self) -> list[int]:
        if not self._page_offsets:
            return []
        vadj = self.scrolled.get_vadjustment()
        if vadj is None:
            return [0]
        top = vadj.get_value()
        bottom = top + vadj.get_page_size()
        visible = []
        for index, offset in enumerate(self._page_offsets):
            height = self._page_widgets[index].get_height()
            if height <= 0:
                height = max(1, int(round(self._page_sizes[index][1] * self._fit_scale)))
            if offset + height >= top and offset <= bottom:
                visible.append(index)
        return visible

    def _scroll_to_offset(self, offset: int, animate: bool = True) -> None:
        vadj = self.scrolled.get_vadjustment()
        if vadj is None:
            return
        upper = max(0.0, vadj.get_upper() - vadj.get_page_size())
        target = max(0.0, min(upper, float(offset)))

        animations = True
        settings = Gtk.Settings.get_default()
        if settings is not None:
            try:
                animations = bool(settings.get_property("gtk-enable-animations"))
            except Exception:
                animations = True

        if not animate or not animations or abs(target - vadj.get_value()) < 2:
            self._cancel_scroll_animation()
            vadj.set_value(target)
            return

        self._cancel_scroll_animation()
        start = vadj.get_value()
        started_at = GLib.get_monotonic_time()

        def tick() -> bool:
            elapsed = (GLib.get_monotonic_time() - started_at) / 1000.0
            progress = min(1.0, elapsed / SCROLL_ANIMATION_MS)
            eased = 1 - (1 - progress) ** 3
            vadj.set_value(start + (target - start) * eased)
            if progress >= 1.0:
                self._scroll_anim_id = 0
                self._update_visible_pages()
                return False
            return True

        self._scroll_anim_id = GLib.timeout_add(16, tick)

    def _cancel_scroll_animation(self) -> None:
        if self._scroll_anim_id:
            GLib.source_remove(self._scroll_anim_id)
            self._scroll_anim_id = 0

    def previous_page(self) -> None:
        page = max(0, self._current_page() - 1)
        self._go_to_page(page)

    def next_page(self) -> None:
        last = max(0, self._rendered_page_count - 1)
        page = min(last, self._current_page() + 1)
        self._go_to_page(page)

    def first_page(self) -> None:
        self._go_to_page(0)

    def last_page(self) -> None:
        self._go_to_page(max(0, self._rendered_page_count - 1))

    def _go_to_page(self, page: int, animate: bool = True) -> None:
        if not self._page_offsets:
            return
        page = max(0, min(len(self._page_offsets) - 1, page))
        # A long jump would animate past unrendered pages; land directly.
        if abs(page - self._current_page()) > 3:
            animate = False
        target = max(0, self._page_offsets[page])
        self._scroll_to_offset(target, animate=animate)
        self._queue_render(page)
        self._update_page_buttons()

    def _on_key_pressed(self, controller, keyval, keycode, state) -> bool:
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        if keyval == Gdk.KEY_Page_Down:
            self.next_page()
            return True
        if keyval == Gdk.KEY_Page_Up:
            self.previous_page()
            return True
        if keyval == Gdk.KEY_Home:
            self.first_page()
            return True
        if keyval == Gdk.KEY_End:
            self.last_page()
            return True
        return False

    # ------------------------------------------------------------- rendering

    def _queue_render(self, index: int) -> None:
        if index < 0 or index >= self._rendered_page_count:
            return
        if index in self._rendered or index in self._render_queue:
            return
        self._render_queue.append(index)
        if not self._render_idle_id:
            self._render_idle_id = GLib.idle_add(
                self._process_render_queue, priority=GLib.PRIORITY_DEFAULT_IDLE
            )

    def _process_render_queue(self) -> bool:
        self._render_idle_id = 0
        if self._tearing_down or not self._render_queue:
            self._render_queue.clear()
            return False

        current = self._current_page()
        # A long jump leaves stale entries behind; dropping them keeps the
        # cache bounded and avoids rasterising pages the user flew past.
        self._render_queue = [
            index
            for index in self._render_queue
            if abs(index - current) <= CACHE_RADIUS + 1
        ]
        if not self._render_queue:
            self._evict_far_pages()
            return False

        index = min(self._render_queue, key=lambda item: abs(item - current))
        self._render_queue.remove(index)
        self._render_page(index)
        self._evict_far_pages()

        if self._render_queue and not self._tearing_down:
            self._render_idle_id = GLib.idle_add(
                self._process_render_queue, priority=GLib.PRIORITY_DEFAULT_IDLE
            )
        return False

    def _render_page(self, index: int) -> None:
        if self._doc is None or index in self._rendered:
            return
        if index < 0 or index >= self._rendered_page_count:
            return

        try:
            page = self._doc.get_page(index)
            page_w, page_h = page.get_size()
            if page_w <= 0 or page_h <= 0:
                return

            device_scale = max(1, int(self.get_scale_factor() or 1))
            scale = self._fit_scale * device_scale
            pixel_w = max(1, int(round(page_w * scale)))
            pixel_h = max(1, int(round(page_h * scale)))
            if pixel_w * pixel_h > MAX_PAGE_PIXELS:
                shrink = (MAX_PAGE_PIXELS / (pixel_w * pixel_h)) ** 0.5
                pixel_w = max(1, int(pixel_w * shrink))
                pixel_h = max(1, int(pixel_h * shrink))

            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixel_w, pixel_h)
            context = cairo.Context(surface)
            context.scale(pixel_w / page_w, pixel_h / page_h)
            context.set_source_rgb(1.0, 1.0, 1.0)
            context.paint()
            page.render(context)

            data = bytes(surface.get_data())
            texture = Gdk.MemoryTexture.new(
                pixel_w,
                pixel_h,
                Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                GLib.Bytes.new(data),
                surface.get_stride(),
            )
            self._textures[index] = texture
            self._page_widgets[index].set_paintable(texture)
            self._rendered.add(index)
        except Exception:
            logger.exception("Could not render PDF page %s of %s", index + 1, self.file_path)

    def _clear_texture(self, index: int) -> None:
        self._rendered.discard(index)
        self._textures.pop(index, None)
        if 0 <= index < len(self._page_widgets):
            try:
                self._page_widgets[index].set_paintable(None)
            except Exception:
                logger.debug("Could not clear PDF page %s", index, exc_info=True)

    def _clear_all_textures(self) -> None:
        for index in list(self._rendered):
            self._clear_texture(index)
        self._render_queue.clear()

    def _evict_far_pages(self) -> None:
        current = self._current_page()
        for index in list(self._rendered):
            if abs(index - current) > CACHE_RADIUS:
                self._clear_texture(index)

    def _update_visible_pages(self) -> None:
        if self._tearing_down or not self._page_offsets:
            return
        visible = self._visible_indices()
        current = self._current_page()

        for index in visible:
            for neighbor in range(index - 1, index + 2):
                self._queue_render(neighbor)

        # Evict textures far from the viewport so a long document cannot
        # accumulate hundreds of page bitmaps.
        self._evict_far_pages()

        if current != self._last_current_page:
            self._last_current_page = current
            self._update_page_buttons()
            self._notify_status_changed()

    def _update_page_buttons(self) -> None:
        current = self._current_page()
        last = max(0, self._rendered_page_count - 1)
        self.btn_prev.set_sensitive(current > 0)
        self.btn_next.set_sensitive(current < last)

    # ------------------------------------------------------------- contract

    def get_header_controls(self) -> list:
        if self._rendered_page_count <= 1:
            return []
        return [self.btn_prev, self.btn_next]

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def set_ready_callback(self, callback) -> None:
        self._ready_callback = callback

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callable(callback):
            try:
                callback()
            except Exception:
                logger.exception("PDF status callback failed")

    def _notify_ready(self) -> None:
        callback = self._ready_callback
        if callable(callback):
            try:
                callback()
            except Exception:
                logger.exception("PDF ready callback failed")

    def _size_text(self) -> str:
        if self._file_size is None:
            return _("Unknown")
        return format_size(self._file_size)

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._rendered_page_count > 0:
            current = min(self._current_page() + 1, self._rendered_page_count)
            page_text = f"{current} / {self._page_count:,}"
        else:
            page_text = _("Unknown")
        return [
            (_("Page"), page_text),
            (_("Size"), self._size_text()),
        ]

    def teardown(self) -> None:
        """Stop timers and release every rendered page."""
        self._tearing_down = True
        self._cancel_scroll_animation()
        if self._render_idle_id:
            GLib.source_remove(self._render_idle_id)
            self._render_idle_id = 0
        if self._size_poll_id:
            GLib.source_remove(self._size_poll_id)
            self._size_poll_id = 0
        self._render_queue.clear()
        self._clear_all_textures()
        self._page_widgets.clear()
        self._page_sizes.clear()
        self._page_offsets.clear()
        self._doc = None
        self._status_callback = None
        self._ready_callback = None

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        target_w = min(980, max(560, int(screen_w * 0.80)))
        if self._page_sizes:
            page_w, page_h = self._page_sizes[0]
            ratio = page_h / max(1.0, page_w)
        else:
            ratio = 842.0 / 595.0
        target_h = int(target_w * ratio) + CHROME_HEIGHT
        target_h = min(int(screen_h * 0.82), max(420, target_h))
        return target_w, target_h
