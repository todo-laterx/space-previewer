import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from utils.formatters import format_size

class ImageViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.zoom_factor = 1.0
        self.pixbuf_orig = None

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

        # Scroll controller for Zoom
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)

    def load_image(self):
        try:
            self.pixbuf_orig = GdkPixbuf.Pixbuf.new_from_file(self.file_path)
            w = self.pixbuf_orig.get_width()
            h = self.pixbuf_orig.get_height()
            size = os.path.getsize(self.file_path)

            self.lbl_dims.set_text(f"{w} × {h} px")
            self.lbl_size.set_text(format_size(size))

            texture = Gdk.Texture.new_for_pixbuf(self.pixbuf_orig)
            self.picture.set_paintable(texture)
        except Exception as e:
            err_label = Gtk.Label(label=f"Could not load image: {e}")
            self.center_box.remove(self.picture)
            self.center_box.append(err_label)

    def on_scroll(self, controller, dx, dy):
        if dy < 0:
            self.zoom_factor = min(self.zoom_factor * 1.15, 5.0)
        else:
            self.zoom_factor = max(self.zoom_factor / 1.15, 0.2)

        if self.pixbuf_orig:
            w = int(self.pixbuf_orig.get_width() * self.zoom_factor)
            h = int(self.pixbuf_orig.get_height() * self.zoom_factor)
            scaled = self.pixbuf_orig.scale_simple(max(1, w), max(1, h), GdkPixbuf.InterpType.BILINEAR)
            if scaled:
                texture = Gdk.Texture.new_for_pixbuf(scaled)
                self.picture.set_paintable(texture)
                self.lbl_dims.set_text(f"{self.pixbuf_orig.get_width()} × {self.pixbuf_orig.get_height()} px ({int(self.zoom_factor * 100)}%)")
        return True

    def get_desired_size(self, screen_w: int, screen_h: int):
        if not self.pixbuf_orig:
            return 900, 650

        orig_w = self.pixbuf_orig.get_width()
        orig_h = self.pixbuf_orig.get_height()
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
