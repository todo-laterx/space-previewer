import os
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

from utils.formatters import format_size

class MediaViewer(Gtk.Box):
    def __init__(self, file_path: str, is_audio: bool = False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.is_audio = is_audio

        self.center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.center_box.set_hexpand(True)
        self.center_box.set_vexpand(True)
        self.center_box.set_halign(Gtk.Align.CENTER)
        self.center_box.set_valign(Gtk.Align.CENTER)
        self.append(self.center_box)

        file = Gio.File.new_for_path(os.path.abspath(file_path))
        self.video = Gtk.Video.new_for_file(file)
        self.video.set_autoplay(True)
        self.video.set_hexpand(True)
        self.video.set_vexpand(True)

        if is_audio:
            # Audio icon badge
            icon = Gtk.Image.new_from_icon_name("audio-x-generic")
            icon.set_pixel_size(96)
            icon.set_margin_top(32)
            self.center_box.append(icon)

            lbl_name = Gtk.Label(label=os.path.basename(file_path))
            lbl_name.add_css_class("title-3")
            self.center_box.append(lbl_name)

            self.video.set_size_request(-1, 48)
            self.center_box.append(self.video)
        else:
            self.center_box.append(self.video)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_info = Gtk.Label(label=format_size(os.path.getsize(file_path)))
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)
