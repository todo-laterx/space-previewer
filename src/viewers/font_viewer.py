import os
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango

from utils.formatters import format_size

class FontViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.content_box.set_margin_start(24)
        self.content_box.set_margin_end(24)
        self.content_box.set_margin_top(24)
        self.content_box.set_margin_bottom(24)
        self.scrolled.set_child(self.content_box)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_info = Gtk.Label(label=f"Font file • {format_size(os.path.getsize(file_path))}")
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)

        self.load_font_preview()

    def load_font_preview(self):
        font_name = os.path.splitext(os.path.basename(self.file_path))[0]

        title = Gtk.Label(label=font_name)
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        self.content_box.append(title)

        sample_pangram = "The quick brown fox jumps over the lazy dog"
        sample_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789 !@#$%^&*()_+-=[]{}|;':\",./<>?"

        chars_label = Gtk.Label(label=sample_chars)
        chars_label.set_halign(Gtk.Align.START)
        chars_label.add_css_class("body")
        self.content_box.append(chars_label)

        sizes = [14, 18, 24, 36, 48]
        for s in sizes:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            size_tag = Gtk.Label(label=f"{s}pt")
            size_tag.add_css_class("caption")
            size_tag.add_css_class("dim-label")
            size_tag.set_halign(Gtk.Align.START)

            sample_lbl = Gtk.Label(label=sample_pangram)
            sample_lbl.set_halign(Gtk.Align.START)
            sample_lbl.set_wrap(True)
            # Custom font size style
            sample_lbl.set_markup(f"<span size='{s*1024}'>{sample_pangram}</span>")

            box.append(size_tag)
            box.append(sample_lbl)
            self.content_box.append(box)
