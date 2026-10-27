import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GObject, Pango

from utils.formatters import format_size
from utils.i18n import _
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
        exp = 0
        idx = 0
        for char in reversed(col_str):
            idx += (ord(char.upper()) - ord('A') + 1) * (26 ** exp)
            exp += 1
        return idx - 1

    def load_spreadsheet(self):
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == ".xlsx":
            self.load_xlsx()
        else:
            self.load_legacy_xls()

    def load_xlsx(self):
        try:
            with open_office_zip(self.file_path) as zf:
                entries = zf.namelist()

                # 1. Parse shared strings
                shared_strings = []
                if "xl/sharedStrings.xml" in entries:
                    root_ss = read_xml(zf, "xl/sharedStrings.xml")
                    for si in root_ss.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                        t_parts = []
                        for t in si.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
                            if t.text:
                                t_parts.append(t.text)
                        shared_strings.append("".join(t_parts))

                # 2. Get sheet names from workbook
                sheet_names = []
                if "xl/workbook.xml" in entries:
                    root_wb = read_xml(zf, "xl/workbook.xml")
                    for s in root_wb.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                        name = s.attrib.get("name")
                        if not name:
                            name = _("Sheet %(number)s") % {
                                "number": len(sheet_names) + 1
                            }
                        sheet_names.append(name)

                # 3. Read sheet1
                sheet_file = "xl/worksheets/sheet1.xml"
                if sheet_file not in entries:
                    sheets = [
                        f for f in entries
                        if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")
                    ]
                    if sheets:
                        sheet_file = sheets[0]
                    else:
                        self._sheet_count = len(sheet_names)
                        self._sheet_name = sheet_names[0] if sheet_names else ""
                        self._update_info()
                        self.scrolled.set_child(Gtk.Label(label=_("No sheets found in spreadsheet.")))
                        return

                root_sheet = read_xml(zf, sheet_file)
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

                grid_data = []
                max_cols = 0

                for row_elem in root_sheet.findall(".//s:row", ns):
                    if len(grid_data) >= 500: # Limit 500 rows preview
                        break

                    row_dict = {}
                    for c in row_elem.findall("s:c", ns):
                        ref = c.attrib.get("r", "")
                        match = re.match(r"([A-Za-z]+)([0-9]+)", ref)
                        if not match:
                            continue
                        col_str = match.group(1)
                        c_idx = self.col_to_index(col_str)

                        # Cell type: 's' for shared string, 'inlineStr', 'b' for boolean, 'e' for error
                        cell_type = c.attrib.get("t", "")
                        val = ""
                        v_elem = c.find("s:v", ns)
                        if cell_type == "s" and v_elem is not None and v_elem.text:
                            try:
                                val = shared_strings[int(v_elem.text)]
                            except (IndexError, ValueError):
                                val = v_elem.text
                        elif cell_type == "inlineStr":
                            t_elem = c.find(".//s:t", ns)
                            if t_elem is not None and t_elem.text:
                                val = t_elem.text
                        elif v_elem is not None and v_elem.text:
                            val = v_elem.text

                        row_dict[c_idx] = val
                        if c_idx + 1 > max_cols:
                            max_cols = c_idx + 1

                    grid_data.append(row_dict)

                self._sheet_count = len(sheet_names) if sheet_names else 1
                self._sheet_name = (
                    sheet_names[0]
                    if sheet_names
                    else _("Sheet %(number)s") % {"number": 1}
                )

                if not grid_data:
                    self._row_count = 0
                    self._col_count = 0
                    self._update_info()
                    self.scrolled.set_child(Gtk.Label(label=_("Spreadsheet is empty.")))
                    return

                # Convert grid_data to 2D rows
                max_cols = min(max_cols, 50) # Max 50 cols
                full_rows = []
                for r_dict in grid_data:
                    row_list = [r_dict.get(c, "") for c in range(max_cols)]
                    full_rows.append(row_list)

                headers = full_rows[0]
                data_rows = full_rows[1:]

                # Generate column labels (A, B, C...)
                def get_col_letter(n):
                    result = ""
                    while n >= 0:
                        result = chr(n % 26 + 65) + result
                        n = n // 26 - 1
                    return result

                col_names = []
                for idx in range(max_cols):
                    h_val = headers[idx] if idx < len(headers) else ""
                    letter = get_col_letter(idx)
                    col_names.append(
                        _("%(letter)s: %(header)s") % {"letter": letter, "header": h_val}
                        if h_val.strip()
                        else letter
                    )

                # Create ListStore
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

                self._row_count = len(grid_data)
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
