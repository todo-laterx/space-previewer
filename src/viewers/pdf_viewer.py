import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib

try:
    gi.require_version('Poppler', '0.18')
    from gi.repository import Poppler
    import cairo
    HAS_POPPLER = True
except Exception:
    HAS_POPPLER = False

from utils.formatters import format_size

class PDFViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path

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

    def load_pdf(self):
        if not HAS_POPPLER:
            self.pages_box.append(Gtk.Label(label="Poppler library is not installed for PDF rendering."))
            return

        try:
            uri = f"file://{os.path.abspath(self.file_path)}"
            doc = Poppler.Document.new_from_file(uri, None)
            n_pages = doc.get_n_pages()

            size = os.path.getsize(self.file_path)
            self.lbl_info.set_text(f"{n_pages} pages • {format_size(size)}")

            # Render up to 20 pages preview
            render_count = min(n_pages, 20)
            for i in range(render_count):
                page = doc.get_page(i)
                w, h = page.get_size()
                scale = 1.5
                img_w = int(w * scale)
                img_h = int(h * scale)

                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, img_w, img_h)
                ctx = cairo.Context(surface)
                ctx.scale(scale, scale)
                # White background
                ctx.set_source_rgb(1.0, 1.0, 1.0)
                ctx.paint()
                page.render(ctx)

                data = surface.get_data()
                bytes_data = GLib.Bytes.new(data.tobytes())
                pixbuf = Gdk.Texture.new_for_pixbuf(
                    Gdk.Pixbuf.new_from_bytes(
                        bytes_data,
                        Gdk.Colorspace.RGB,
                        True,
                        8,
                        img_w,
                        img_h,
                        surface.get_stride()
                    )
                ) if hasattr(Gdk, 'Pixbuf') else None

                picture = Gtk.Picture.new_for_paintable(
                    Gdk.Texture.new_for_pixbuf(
                        Gdk.Pixbuf.new_from_data(
                            data.tobytes(),
                            GdkPixbuf.Colorspace.RGB,
                            True,
                            8,
                            img_w,
                            img_h,
                            surface.get_stride()
                        )
                    ) if False else Gdk.MemoryTexture.new(
                        img_w,
                        img_h,
                        Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                        bytes_data,
                        surface.get_stride()
                    )
                )
                picture.set_can_shrink(True)
                picture.add_css_class("card")
                self.pages_box.append(picture)

            if n_pages > 20:
                more_lbl = Gtk.Label(label=f"... [Showing first 20 of {n_pages} pages] ...")
                more_lbl.add_css_class("dim-label")
                self.pages_box.append(more_lbl)

        except Exception as e:
            self.pages_box.append(Gtk.Label(label=f"Could not load PDF:\n{e}"))
