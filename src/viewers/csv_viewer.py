"""CSV/TSV preview: a bounded table built with a streaming reader."""

from __future__ import annotations

import csv
import logging
import os
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GObject, Gtk, Pango

from utils.formatters import format_size
from utils.i18n import _, ngettext

logger = logging.getLogger(__name__)

# Untrusted-input limits for tabular previews.
MAX_CSV_ROWS = 5000
MAX_CSV_COLUMNS = 100
SNIFF_BYTES = 4096

StatusCallback = Callable[[], None]


class CSVRow(GObject.Object):
    def __init__(self, values):
        super().__init__()
        self.values = values


class CSVViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.row_count = 0

        self._column_count = 0
        self._file_size = self._safe_file_size()
        self._load_failed = False
        self._status_callback: Optional[StatusCallback] = None

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

        self.lbl_note = Gtk.Label()
        self.lbl_note.add_css_class("dim-label")
        self.lbl_note.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_note.set_hexpand(True)
        self.info_bar.append(self.lbl_note)

        self.append(self.info_bar)

        self.load_csv()

    def _safe_file_size(self) -> int:
        try:
            return os.path.getsize(self.file_path)
        except OSError:
            return 0

    # ---------------------------------------------------------------- loading

    def load_csv(self) -> None:
        if self.file_path.lower().endswith((".tsv", ".tab")):
            delimiter = "\t"
        else:
            delimiter = ","

        headers: Optional[list[str]] = None
        data_rows: list[list[str]] = []
        truncated_rows = False
        truncated_columns = False

        try:
            with open(
                self.file_path, "r", encoding="utf-8", errors="replace", newline=""
            ) as handle:
                # Sniff a bounded sample only; the rest is streamed.
                sample = handle.read(SNIFF_BYTES)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
                    delimiter = dialect.delimiter
                except csv.Error:
                    pass

                reader = csv.reader(handle, delimiter=delimiter)
                for row in reader:
                    if headers is None:
                        if not row:
                            continue
                        if len(row) > MAX_CSV_COLUMNS:
                            truncated_columns = True
                            headers = row[:MAX_CSV_COLUMNS]
                        else:
                            headers = row
                        continue

                    if not row:
                        continue

                    if len(data_rows) >= MAX_CSV_ROWS:
                        truncated_rows = True
                        break

                    if len(row) > MAX_CSV_COLUMNS:
                        truncated_columns = True

                    if len(row) < len(headers):
                        row = row + [""] * (len(headers) - len(row))
                    elif len(row) > len(headers):
                        row = row[: len(headers)]

                    data_rows.append(row)

        except (OSError, UnicodeError, csv.Error) as exc:
            self._show_message(
                _("Could not parse CSV: {error}").format(error=exc),
                failed=True,
            )
            return
        except Exception as exc:
            logger.exception("CSV parse failed for %s", self.file_path)
            self._show_message(
                _("Could not parse CSV: {error}").format(error=exc),
                failed=True,
            )
            return

        if headers is None:
            self._show_message(_("CSV file is empty."), failed=False)
            return

        self.row_count = len(data_rows)
        self._column_count = len(headers)

        # Create ListStore
        store = Gio.ListStore.new(CSVRow)
        for row in data_rows:
            store.append(CSVRow(row))

        sel_model = Gtk.SingleSelection.new(store)
        column_view = Gtk.ColumnView.new(sel_model)
        column_view.set_show_row_separators(True)
        column_view.set_show_column_separators(True)

        for col_idx, col_name in enumerate(headers):
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._factory_setup)
            factory.connect("bind", self._factory_bind, col_idx)

            if not str(col_name).strip():
                title = _("Column {number}").format(number=col_idx + 1)
            else:
                title = col_name
            col = Gtk.ColumnViewColumn.new(title, factory)
            col.set_resizable(True)
            column_view.append_column(col)

        self.scrolled.set_child(column_view)
        self._update_info_bar(truncated_rows, truncated_columns)
        self._notify_status_changed()

    def _update_info_bar(
        self, truncated_rows: bool, truncated_columns: bool
    ) -> None:
        rows_text = ngettext(
            "{count} row", "{count} rows", self.row_count
        ).format(count=f"{self.row_count:,}")
        columns_text = ngettext(
            "{count} column", "{count} columns", self._column_count
        ).format(count=f"{self._column_count:,}")

        self.lbl_info.set_text(
            _("{rows}, {columns}, {size}").format(
                rows=rows_text,
                columns=columns_text,
                size=format_size(self._file_size),
            )
        )

        if truncated_rows and truncated_columns:
            note = _(
                "Preview truncated at {rows} rows and {columns} columns."
            ).format(
                rows=f"{MAX_CSV_ROWS:,}",
                columns=f"{MAX_CSV_COLUMNS:,}",
            )
        elif truncated_rows:
            note = _("Preview truncated at {rows} rows.").format(
                rows=f"{MAX_CSV_ROWS:,}"
            )
        elif truncated_columns:
            note = _("Preview truncated at {columns} columns.").format(
                columns=f"{MAX_CSV_COLUMNS:,}"
            )
        else:
            note = ""
        self.lbl_note.set_text(note)

    def _show_message(self, message: str, failed: bool) -> None:
        self._load_failed = failed
        self.row_count = 0
        self._column_count = 0
        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.CENTER)
        self.scrolled.set_child(label)
        self.lbl_info.set_text("")
        self.lbl_note.set_text("")
        self._notify_status_changed()

    # -------------------------------------------------------------- factories

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

    # ------------------------------------------------------------------ state

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("CSV status callback failed")

    def set_status_callback(self, callback: Optional[StatusCallback]) -> None:
        """Register a callback invoked when the status metadata changes."""
        self._status_callback = callback if callable(callback) else None

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._load_failed:
            return [
                (_("Rows"), _("Unavailable")),
                (_("Columns"), _("Unavailable")),
                (_("Size"), format_size(self._file_size)),
            ]

        return [
            (_("Rows"), f"{self.row_count:,}"),
            (_("Columns"), f"{self._column_count:,}"),
            (_("Size"), format_size(self._file_size)),
        ]

    def teardown(self) -> None:
        """No asynchronous resources are owned; the method is part of the contract."""
        self._status_callback = None

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(1180, int(screen_w * 0.85))
        content_h = 140 + min(self.row_count, 25) * 32
        min_h = 380
        max_h = min(880, int(screen_h * 0.82))
        return target_w, max(min_h, min(max_h, content_h))
