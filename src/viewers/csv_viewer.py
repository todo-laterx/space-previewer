import os
import csv
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GObject, Pango

from utils.formatters import format_size

class CSVRow(GObject.Object):
    def __init__(self, values):
        super().__init__()
        self.values = values

class CSVViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.row_count = 0

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

        self.load_csv()

    def load_csv(self):
        try:
            delimiter = "\t" if self.file_path.endswith(".tsv") else ","
            rows = []
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                # Sniff dialect if possible
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
                    delimiter = dialect.delimiter
                except Exception:
                    pass

                reader = csv.reader(f, delimiter=delimiter)
                for i, r in enumerate(reader):
                    if i > 500: # Max 500 rows preview
                        break
                    rows.append(r)

            if not rows:
                self.scrolled.set_child(Gtk.Label(label="CSV file is empty."))
                return

            headers = rows[0]
            data_rows = rows[1:]
            self.row_count = len(data_rows)

            # Create ListStore
            store = Gio.ListStore.new(CSVRow)
            for r in data_rows:
                # Pad row to match header length
                padded = r + [""] * (len(headers) - len(r))
                store.append(CSVRow(padded))

            sel_model = Gtk.SingleSelection.new(store)
            column_view = Gtk.ColumnView.new(sel_model)
            column_view.set_show_row_separators(True)
            column_view.set_show_column_separators(True)

            for col_idx, col_name in enumerate(headers):
                factory = Gtk.SignalListItemFactory()
                factory.connect("setup", self._factory_setup)
                factory.connect("bind", self._factory_bind, col_idx)

                col = Gtk.ColumnViewColumn.new(col_name if col_name.strip() else f"Col {col_idx+1}", factory)
                col.set_resizable(True)
                column_view.append_column(col)

            self.scrolled.set_child(column_view)
            size = os.path.getsize(self.file_path)
            self.lbl_info.set_text(f"{len(headers)} columns • {len(data_rows):,} rows • {format_size(size)}")

        except Exception as e:
            self.scrolled.set_child(Gtk.Label(label=f"Could not parse CSV:\n{e}"))

    def _factory_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(40)
        list_item.set_child(label)

    def _factory_bind(self, factory, list_item, col_idx):
        item = list_item.get_item()
        label = list_item.get_child()
        if item and col_idx < len(item.values):
            label.set_text(str(item.values[col_idx]))
        else:
            label.set_text("")

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        content_h = 140 + min(self.row_count, 25) * 32
        min_h = 380
        max_h = min(880, int(screen_h * 0.82))
        return target_w, max(min_h, min(max_h, content_h))
