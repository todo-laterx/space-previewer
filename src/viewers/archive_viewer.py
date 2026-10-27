import os
import zipfile
import tarfile
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GObject, Pango

from utils.formatters import format_size, format_date

class ArchiveItem(GObject.Object):
    def __init__(self, name: str, size: int, is_dir: bool, date_str: str):
        super().__init__()
        self.name = name
        self.size = size
        self.is_dir = is_dir
        self.date_str = date_str

class ArchiveViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

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

        self.load_archive()

    def load_archive(self):
        items = []
        total_uncompressed = 0
        try:
            if zipfile.is_zipfile(self.file_path):
                with zipfile.ZipFile(self.file_path, "r") as zf:
                    for info in zf.infolist():
                        dt_str = f"{info.date_time[0]}-{info.date_time[1]:02d}-{info.date_time[2]:02d} {info.date_time[3]:02d}:{info.date_time[4]:02d}"
                        items.append(ArchiveItem(info.filename, info.file_size, info.is_dir(), dt_str))
                        total_uncompressed += info.file_size
            elif tarfile.is_tarfile(self.file_path):
                with tarfile.open(self.file_path, "r:*") as tf:
                    for member in tf.getmembers():
                        dt_str = format_date(member.mtime) if member.mtime else ""
                        items.append(ArchiveItem(member.name, member.size, member.isdir(), dt_str))
                        total_uncompressed += member.size
            else:
                self.scrolled.set_child(Gtk.Label(label="Unsupported archive format or corrupted file."))
                return

            if not items:
                self.scrolled.set_child(Gtk.Label(label="Archive is empty."))
                return

            store = Gio.ListStore.new(ArchiveItem)
            for item in items:
                store.append(item)

            sel_model = Gtk.SingleSelection.new(store)
            column_view = Gtk.ColumnView.new(sel_model)
            column_view.set_show_row_separators(True)
            column_view.set_show_column_separators(True)

            # Name column
            factory_name = Gtk.SignalListItemFactory()
            factory_name.connect("setup", self._factory_setup_name)
            factory_name.connect("bind", self._factory_bind_name)
            col_name = Gtk.ColumnViewColumn.new("File Name", factory_name)
            col_name.set_expand(True)
            col_name.set_resizable(True)
            column_view.append_column(col_name)

            # Size column
            factory_size = Gtk.SignalListItemFactory()
            factory_size.connect("setup", self._factory_setup_label)
            factory_size.connect("bind", self._factory_bind_size)
            col_size = Gtk.ColumnViewColumn.new("Size", factory_size)
            col_size.set_fixed_width(100)
            col_size.set_resizable(True)
            column_view.append_column(col_size)

            # Date column
            factory_date = Gtk.SignalListItemFactory()
            factory_date.connect("setup", self._factory_setup_label)
            factory_date.connect("bind", self._factory_bind_date)
            col_date = Gtk.ColumnViewColumn.new("Date Modified", factory_date)
            col_date.set_fixed_width(160)
            col_date.set_resizable(True)
            column_view.append_column(col_date)

            self.scrolled.set_child(column_view)
            archive_size = os.path.getsize(self.file_path)
            self.lbl_info.set_text(
                f"{len(items):,} items • Compressed: {format_size(archive_size)} • Uncompressed: {format_size(total_uncompressed)}"
            )

        except Exception as e:
            self.scrolled.set_child(Gtk.Label(label=f"Could not read archive:\n{e}"))

    def _factory_setup_name(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        icon = Gtk.Image()
        label = Gtk.Label()
        label.set_ellipsize(Pango.EllipsizeMode.END)

        box.append(icon)
        box.append(label)
        list_item.set_child(box)

    def _factory_bind_name(self, factory, list_item):
        item = list_item.get_item()
        box = list_item.get_child()
        icon = box.get_first_child()
        label = icon.get_next_sibling()

        if item:
            icon_name = "folder" if item.is_dir else "text-x-generic"
            icon.set_from_icon_name(icon_name)
            label.set_text(item.name)

    def _factory_setup_label(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        list_item.set_child(label)

    def _factory_bind_size(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        if item:
            label.set_text("-" if item.is_dir else format_size(item.size))

    def _factory_bind_date(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        if item:
            label.set_text(item.date_str)
