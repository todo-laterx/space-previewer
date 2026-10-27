import logging
import os

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib

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
from utils.i18n import _, ngettext

# Untrusted input cap: render at most this many pages of a PDF.
MAX_PAGES = 100


class PDFViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self._status_callback = None
        self._page_count = 0

        try:
            self._file_size = os.path.getsize(file_path)
        except OSError:
            self._file_size = None

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.pages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.pages_box.set_halign(Gtk.Align.CENTER)
        self.pages_box.set_margin_top(16)
        self.pages_box.set_margin_bottom(16)
        self.scrolled.set_child(self.pages_box)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_info = Gtk.Label()
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)

        self.load_pdf()

    def load_pdf(self) -> None:
        if not HAS_POPPLER:
            self.pages_box.append(
                Gtk.Label(
                    label=_("Poppler library is not installed for PDF rendering.")
                )
            )
            self.lbl_info.set_text(self._size_text())
            return

        try:
            uri = GLib.filename_to_uri(os.path.abspath(self.file_path), None)
            doc = Poppler.Document.new_from_file(uri, None)
            n_pages = int(doc.get_n_pages())
            self._page_count = n_pages

            page_text = ngettext(
                "{count} page", "{count} pages", n_pages
            ).format(count=f"{n_pages:,}")
            self.lbl_info.set_text(
                _("{pages} • {size}").format(
                    pages=page_text, size=self._size_text()
                )
            )

            # Render only the capped number of pages, but report the real
            # page count in the status bar and info line.
            render_count = min(n_pages, MAX_PAGES)
            for index in range(render_count):
                self._render_page(doc, index)

            if n_pages > MAX_PAGES:
                more_lbl = Gtk.Label(
                    label=_("Showing the first {shown} of {total} pages.").format(
                        shown=MAX_PAGES, total=n_pages
                    )
                )
                more_lbl.add_css_class("dim-label")
                more_lbl.set_wrap(True)
                self.pages_box.append(more_lbl)

        except Exception as error:
            logger.exception("Could not load PDF %s", self.file_path)
            self.pages_box.append(
                Gtk.Label(
                    label=_("Could not load PDF:\n{error}").format(error=error)
                )
            )

    def _render_page(self, doc, index: int) -> None:
        page = doc.get_page(index)
        width, height = page.get_size()
        if width <= 0 or height <= 0:
            return

        scale = 1.5
        img_w = int(width * scale)
        img_h = int(height * scale)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, img_w, img_h)
        ctx = cairo.Context(surface)
        ctx.scale(scale, scale)
        # White background
        ctx.set_source_rgb(1.0, 1.0, 1.0)
        ctx.paint()
        page.render(ctx)

        data = surface.get_data()
        bytes_data = GLib.Bytes.new(data.tobytes())
        texture = Gdk.MemoryTexture.new(
            img_w,
            img_h,
            Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
            bytes_data,
            surface.get_stride(),
        )
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_can_shrink(True)
        picture.add_css_class("card")
        self.pages_box.append(picture)

    # ------------------------------------------------------------- contract

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def _size_text(self) -> str:
        if self._file_size is None:
            return _("Unknown")
        return format_size(self._file_size)

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._page_count > 0:
            page_text = f"{self._page_count:,}"
        else:
            page_text = _("Unknown")
        return [
            (_("Pages"), page_text),
            (_("Size"), self._size_text()),
        ]

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        width = min(1040, int(screen_w * 0.85))
        height = min(900, int(screen_h * 0.85))
        return width, height

    def teardown(self) -> None:
        """Clear rendered pages and drop the window callback."""
        child = self.pages_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.pages_box.remove(child)
            child = next_child
        self._page_count = 0
        self._status_callback = None
