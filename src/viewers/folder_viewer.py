import os
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, Pango

from utils.formatters import format_size, format_date

class FolderViewer(Gtk.Box):
    def __init__(self, folder_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.folder_path = folder_path
        self.item_count = 0

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
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

        self.lbl_info = Gtk.Label()
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)

        self.load_folder_info()

    def load_folder_info(self):
        folder_name = os.path.basename(os.path.abspath(self.folder_path))

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("folder")
        icon.set_pixel_size(48)
        header_box.append(icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=folder_name)
        lbl_title.add_css_class("title-1")
        lbl_title.set_halign(Gtk.Align.START)
        title_box.append(lbl_title)

        mtime = os.path.getmtime(self.folder_path)
        lbl_date = Gtk.Label(label=f"Modified: {format_date(mtime)}")
        lbl_date.add_css_class("dim-label")
        lbl_date.set_halign(Gtk.Align.START)
        title_box.append(lbl_date)

        header_box.append(title_box)
        self.content_box.append(header_box)

        # Read top items
        try:
            entries = os.listdir(self.folder_path)
            total_items = len(entries)
            self.item_count = total_items
            total_size = 0
            dir_count = 0
            file_count = 0

            preview_list = Gtk.ListBox()
            preview_list.add_css_class("boxed-list")

            for item in sorted(entries)[:30]:
                item_path = os.path.join(self.folder_path, item)
                is_d = os.path.isdir(item_path)
                if is_d:
                    dir_count += 1
                else:
                    file_count += 1
                    try:
                        total_size += os.path.getsize(item_path)
                    except Exception:
                        pass

                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                row.set_margin_start(12)
                row.set_margin_end(12)
                row.set_margin_top(8)
                row.set_margin_bottom(8)

                item_icon = Gtk.Image.new_from_icon_name("folder" if is_d else "text-x-generic")
                row.append(item_icon)

                item_lbl = Gtk.Label(label=item)
                item_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                item_lbl.set_halign(Gtk.Align.START)
                item_lbl.set_hexpand(True)
                row.append(item_lbl)

                if not is_d:
                    try:
                        size_lbl = Gtk.Label(label=format_size(os.path.getsize(item_path)))
                        size_lbl.add_css_class("dim-label")
                        row.append(size_lbl)
                    except Exception:
                        pass

                preview_list.append(row)

            self.content_box.append(preview_list)
            self.lbl_info.set_text(f"{total_items:,} items ({dir_count} folders, {file_count} files)")

        except Exception as e:
            self.content_box.append(Gtk.Label(label=f"Could not read directory:\n{e}"))

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(880, int(screen_w * 0.70))
        displayed_items = min(self.item_count, 25)
        item_h = 38
        content_h = 220 + displayed_items * item_h
        min_h = 360
        max_h = min(780, int(screen_h * 0.75))
        target_h = max(min_h, min(max_h, content_h))
        return target_w, target_h
