import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GObject, Pango

from utils.formatters import format_size
from utils.i18n import _
from utils.parsers import col_to_index, read_xlsx_preview
from viewers.office_common import OfficeParseError, open_office_zip, read_xml

log = logging.getLogger(__name__)

class ExcelRow(GObject.Object):
    def __init__(self, values):
        super().__init__()
        self.values = values

class ExcelViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self._sheet_count = 0
        self._row_count = 0
        self._col_count = 0
        self._sheet_name = ""
        try:
            self._size_bytes = os.path.getsize(file_path)
        except OSError:
            self._size_bytes = 0

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

        self.load_spreadsheet()

    def col_to_index(self, col_str: str) -> int:
        """Convert Excel column letters like A, B, AA to 0-based index."""
        return col_to_index(col_str)

    def load_spreadsheet(self):
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == ".xlsx":
            self.load_xlsx()
        else:
            self.load_legacy_xls()

    def load_xlsx(self):
        try:
            preview = read_xlsx_preview(self.file_path)
            self._sheet_count = preview.sheet_count
            self._sheet_name = preview.sheet_name
            if preview.no_sheets:
                self._update_info()
                self.scrolled.set_child(
                    Gtk.Label(label=_("No sheets found in spreadsheet."))
                )
                return

            if preview.row_count == 0:
                self._row_count = 0
                self._col_count = 0
                self._update_info()
                self.scrolled.set_child(
                    Gtk.Label(label=_("Spreadsheet is empty."))
                )
                return

            max_cols = preview.col_count
            col_names = preview.col_names
            data_rows = preview.data_rows

            store = Gio.ListStore.new(ExcelRow)
            for r in data_rows:
                padded = r + [""] * (max_cols - len(r))
                store.append(ExcelRow(padded))

            sel_model = Gtk.SingleSelection.new(store)
            column_view = Gtk.ColumnView.new(sel_model)
            column_view.set_show_row_separators(True)
            column_view.set_show_column_separators(True)

            for col_idx, col_name in enumerate(col_names):
                factory = Gtk.SignalListItemFactory()
                factory.connect("setup", self._factory_setup)
                factory.connect("bind", self._factory_bind, col_idx)

                col = Gtk.ColumnViewColumn.new(col_name, factory)
                col.set_resizable(True)
                col.set_fixed_width(120)
                column_view.append_column(col)

            self.scrolled.set_child(column_view)

            self._row_count = preview.row_count
            self._col_count = max_cols
            self._update_info()

        except OfficeParseError as exc:
            self.scrolled.set_child(Gtk.Label(
                label=_("Could not load Excel spreadsheet:\n%(error)s")
                % {"error": str(exc)}
            ))
        except Exception:
            log.exception("Could not load Excel spreadsheet %s", self.file_path)
            self.scrolled.set_child(Gtk.Label(
                label=_("Could not load Excel spreadsheet.")
            ))

    def load_legacy_xls(self):
        size = format_size(self._size_bytes)
        self.scrolled.set_child(Gtk.Label(
            label=_(
                "Legacy Excel (.xls) binary spreadsheet.\n"
                "Size: %(size)s\n"
                "Click 'Open with App' to view in full office suite."
            )
            % {"size": size}
        ))
        self.lbl_info.set_text(
            _("Excel Binary (.xls) • %(size)s") % {"size": size}
        )

    def _update_info(self) -> None:
        size = format_size(self._size_bytes)
        if self._sheet_name:
            self.lbl_info.set_text(
                _("Excel (.xlsx) • %(sheet)s • %(cols)s × %(rows)s • %(size)s")
                % {
                    "sheet": self._sheet_name,
                    "cols": f"{self._col_count:,}",
                    "rows": f"{self._row_count:,}",
                    "size": size,
                }
            )
        else:
            self.lbl_info.set_text(
                _("Excel (.xlsx) • %(size)s") % {"size": size}
            )

    def get_status_items(self) -> list[tuple[str, str]]:
        size_item = (_("Size"), format_size(self._size_bytes))
        # A legacy .xls body is not parsed, so do not claim zero sheets and
        # rows for it.
        if os.path.splitext(self.file_path)[1].lower() != ".xlsx":
            return [size_item]
        return [
            (_("Sheets"), f"{self._sheet_count:,}"),
            (_("Rows"), f"{self._row_count:,}"),
            size_item,
        ]

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        return (
            min(1160, int(screen_w * 0.88)),
            min(820, int(screen_h * 0.82)),
        )

    def teardown(self) -> None:
        """The viewer owns no external resources."""

    def _factory_setup(self, factory, list_item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)

    def _factory_bind(self, factory, list_item, col_idx):
        item = list_item.get_item()
        label = list_item.get_child()
        if item and col_idx < len(item.values):
            label.set_text(str(item.values[col_idx]))
        else:
            label.set_text("")
