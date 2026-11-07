"""Archive preview: a bounded listing of ZIP/TAR members, never extracted."""

from __future__ import annotations

import datetime
import logging
import os
import tarfile
import zipfile
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GObject, Gtk, Pango

from utils.formatters import format_date, format_size
from utils.i18n import _, ngettext
from utils.parsers import (
    ArchiveEncryptedError,
    ArchiveFormatError,
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    read_archive_entries,
)

logger = logging.getLogger(__name__)

StatusCallback = Callable[[], None]


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

        self._entry_count = 0
        self._archive_size = self._safe_file_size()
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

        self.load_archive()

    def _safe_file_size(self) -> int:
        try:
            return os.path.getsize(self.file_path)
        except OSError:
            return 0

    # ---------------------------------------------------------------- loading

    def _zip_date(self, info: zipfile.ZipInfo) -> str:
        try:
            return format_date(datetime.datetime(*info.date_time).timestamp())
        except (ValueError, OverflowError, OSError):
            return ""

    def _tar_date(self, member: tarfile.TarInfo) -> str:
        if not member.mtime:
            return ""
        try:
            return format_date(member.mtime)
        except (ValueError, OverflowError, OSError):
            return ""

    def load_archive(self) -> None:
        try:
            preview = read_archive_entries(self.file_path)
        except ArchiveEncryptedError as exc:
            self._show_message(str(exc))
            return
        except ArchiveFormatError as exc:
            self._show_message(str(exc))
            return
        except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as exc:
            self._show_message(
                _("Could not read archive: {error}").format(error=exc)
            )
            return
        except Exception as exc:
            logger.exception("Archive listing failed for %s", self.file_path)
            self._show_message(
                _("Could not read archive: {error}").format(error=exc)
            )
            return

        items = [
            ArchiveItem(e.name, e.size, e.is_dir, e.date_str)
            for e in preview.entries
        ]
        total_uncompressed = preview.total_uncompressed
        truncated = preview.truncated

        if not items:
            if truncated:
                self._show_message(
                    _("The archive exceeds the preview limits.")
                )
            else:
                self._show_message(_("Archive is empty."), failed=False)
            return

        self._entry_count = len(items)

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
        col_name = Gtk.ColumnViewColumn.new(_("File Name"), factory_name)
        col_name.set_expand(True)
        col_name.set_resizable(True)
        column_view.append_column(col_name)

        # Size column
        factory_size = Gtk.SignalListItemFactory()
        factory_size.connect("setup", self._factory_setup_label)
        factory_size.connect("bind", self._factory_bind_size)
        col_size = Gtk.ColumnViewColumn.new(_("Size"), factory_size)
        col_size.set_fixed_width(100)
        col_size.set_resizable(True)
        column_view.append_column(col_size)

        # Date column
        factory_date = Gtk.SignalListItemFactory()
        factory_date.connect("setup", self._factory_setup_label)
        factory_date.connect("bind", self._factory_bind_date)
        col_date = Gtk.ColumnViewColumn.new(_("Date Modified"), factory_date)
        col_date.set_fixed_width(160)
        col_date.set_resizable(True)
        column_view.append_column(col_date)

        self.scrolled.set_child(column_view)

        entries_text = ngettext(
            "{count} entry", "{count} entries", self._entry_count
        ).format(count=f"{self._entry_count:,}")
        self.lbl_info.set_text(
            _(
                "{entries}, {compressed} compressed, "
                "{uncompressed} uncompressed"
            ).format(
                entries=entries_text,
                compressed=format_size(self._archive_size),
                uncompressed=format_size(total_uncompressed),
            )
        )
        if truncated:
            self.lbl_note.set_text(
                _(
                    "Preview truncated at {entries} entries or {size} "
                    "uncompressed."
                ).format(
                    entries=f"{MAX_ARCHIVE_ENTRIES:,}",
                    size=format_size(MAX_ARCHIVE_UNCOMPRESSED_BYTES),
                )
            )
        else:
            self.lbl_note.set_text("")

        self._notify_status_changed()

    def _show_message(self, message: str, failed: bool = True) -> None:
        self._load_failed = failed
        self._entry_count = 0
        error_label = Gtk.Label(label=message)
        error_label.set_wrap(True)
        error_label.set_halign(Gtk.Align.CENTER)
        error_label.set_valign(Gtk.Align.CENTER)
        self.scrolled.set_child(error_label)
        self.lbl_info.set_text("")
        self.lbl_note.set_text("")
        self._notify_status_changed()

    # -------------------------------------------------------------- factories

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

    # ------------------------------------------------------------------ state

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("Archive status callback failed")

    def set_status_callback(self, callback: Optional[StatusCallback]) -> None:
        """Register a callback invoked when the status metadata changes."""
        self._status_callback = callback if callable(callback) else None

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._load_failed:
            return [
                (_("Entries"), _("Unavailable")),
                (_("Archive Size"), format_size(self._archive_size)),
            ]

        return [
            (_("Entries"), f"{self._entry_count:,}"),
            (_("Archive Size"), format_size(self._archive_size)),
        ]

    def teardown(self) -> None:
        """No asynchronous resources are owned; the method is part of the contract."""
        self._status_callback = None

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(980, int(screen_w * 0.75))
        min_h = 380
        max_h = min(860, int(screen_h * 0.82))
        return target_w, min(max_h, max(min_h, 560))
