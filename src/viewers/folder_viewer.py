"""Folder preview with a bounded, cancellable background size scan."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk, Pango

from utils.formatters import format_date, format_size
from utils.i18n import _, ngettext

logger = logging.getLogger(__name__)

# Untrusted-input limits for directory walks. The scan stops at whichever
# limit is reached first so a huge or slow tree can never block the UI.
MAX_SCAN_ENTRIES = 20000
SCAN_TIME_LIMIT_SECONDS = 2.0
# The top-level listing is bounded independently of the recursive scan.
LIST_PREVIEW_COUNT = 30
LIST_SCAN_LIMIT = MAX_SCAN_ENTRIES

StatusCallback = Callable[[], None]


class FolderViewer(Gtk.Box):
    def __init__(self, folder_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.folder_path = folder_path
        self.item_count = 0

        self._total_size = 0
        self._unreadable = 0
        self._calculating = True
        self._scan_truncated = False
        self._listing_truncated = False
        self._read_error = False
        self._scan_failed = False

        # Lifecycle state: the generation counter rejects idle callbacks that
        # belong to a viewer instance that has already been torn down.
        self._cancelled = False
        self._generation = 0
        self._cancel_event = threading.Event()
        self._scan_thread: Optional[threading.Thread] = None
        self._idle_source_id: Optional[int] = None
        self._status_callback: Optional[StatusCallback] = None

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

        self.lbl_note = Gtk.Label()
        self.lbl_note.add_css_class("dim-label")
        self.lbl_note.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_note.set_hexpand(True)
        self.info_bar.append(self.lbl_note)

        self.append(self.info_bar)

        self._load_folder_info()

        if self._read_error:
            self._calculating = False
            self._update_info_bar()
        else:
            self._start_scan()

    # ---------------------------------------------------------------- loading

    def _load_folder_info(self) -> None:
        folder_name = os.path.basename(os.path.abspath(self.folder_path))
        if not folder_name:
            folder_name = self.folder_path

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("folder")
        icon.set_pixel_size(48)
        header_box.append(icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_title = Gtk.Label(label=folder_name)
        lbl_title.add_css_class("title-1")
        lbl_title.set_halign(Gtk.Align.START)
        title_box.append(lbl_title)

        try:
            modified_text = _("Modified: {date}").format(
                date=format_date(os.path.getmtime(self.folder_path))
            )
        except (OSError, ValueError, OverflowError):
            modified_text = _("Modified time unavailable")
        lbl_date = Gtk.Label(label=modified_text)
        lbl_date.add_css_class("dim-label")
        lbl_date.set_halign(Gtk.Align.START)
        title_box.append(lbl_date)

        header_box.append(title_box)
        self.content_box.append(header_box)

        try:
            names = self._read_top_level_names()
        except OSError as exc:
            self._read_error = True
            message = _("Could not read directory: {error}").format(error=exc)
            error_label = Gtk.Label(label=message)
            error_label.set_wrap(True)
            error_label.set_halign(Gtk.Align.START)
            self.content_box.append(error_label)
            return

        self.item_count = len(names)

        if not names:
            empty_label = Gtk.Label(label=_("This folder is empty."))
            empty_label.add_css_class("dim-label")
            empty_label.set_halign(Gtk.Align.START)
            self.content_box.append(empty_label)
            return

        # Sorting a bounded slice keeps large directories predictable.
        preview_names = sorted(names)[:LIST_PREVIEW_COUNT]
        self.content_box.append(self._build_preview_list(preview_names))

    def _read_top_level_names(self) -> list[str]:
        """Read at most ``LIST_SCAN_LIMIT`` top-level names from the folder."""
        names: list[str] = []
        with os.scandir(self.folder_path) as entries:
            iterator = iter(entries)
            for entry in iterator:
                names.append(entry.name)
                if len(names) >= LIST_SCAN_LIMIT:
                    # Peek once so an exactly-at-the-limit folder is not
                    # reported as truncated.
                    if next(iterator, None) is not None:
                        self._listing_truncated = True
                    break
        return names

    def _build_preview_list(self, names: list[str]) -> Gtk.ListBox:
        preview_list = Gtk.ListBox()
        preview_list.add_css_class("boxed-list")

        for item in names:
            item_path = os.path.join(self.folder_path, item)
            is_dir = os.path.isdir(item_path)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_start(12)
            row.set_margin_end(12)
            row.set_margin_top(8)
            row.set_margin_bottom(8)

            item_icon = Gtk.Image.new_from_icon_name(
                "folder" if is_dir else "text-x-generic"
            )
            row.append(item_icon)

            item_lbl = Gtk.Label(label=item)
            item_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            item_lbl.set_halign(Gtk.Align.START)
            item_lbl.set_hexpand(True)
            row.append(item_lbl)

            if not is_dir:
                try:
                    size_value = os.path.getsize(item_path)
                except OSError:
                    size_value = None
                if size_value is not None:
                    size_lbl = Gtk.Label(label=format_size(size_value))
                    size_lbl.add_css_class("dim-label")
                    row.append(size_lbl)

            preview_list.append(row)

        return preview_list

    # ------------------------------------------------------------- background

    def _start_scan(self) -> None:
        """Start the recursive accounting pass without blocking the UI."""
        self._calculating = True
        self._update_info_bar()
        self._notify_status_changed()

        generation = self._generation
        cancel_event = self._cancel_event
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(generation, cancel_event),
            name="space-previewer-folder-scan",
            daemon=True,
        )
        self._scan_thread.start()

    def _scan_worker(self, generation: int, cancel_event: threading.Event) -> None:
        """Walk the tree with entry/time limits and an inode loop guard."""
        total_size = 0
        count = 0
        unreadable = 0
        truncated = False
        visited: set[tuple[int, int]] = set()

        try:
            root_stat = os.stat(self.folder_path)
            visited.add((root_stat.st_dev, root_stat.st_ino))
        except OSError:
            unreadable += 1

        stack = [self.folder_path]
        deadline = time.monotonic() + SCAN_TIME_LIMIT_SECONDS

        try:
            while stack:
                if cancel_event.is_set():
                    return
                if time.monotonic() >= deadline:
                    truncated = True
                    break

                current = stack.pop()
                try:
                    with os.scandir(current) as entries:
                        for entry in entries:
                            if cancel_event.is_set():
                                return
                            if (
                                count >= MAX_SCAN_ENTRIES
                                or time.monotonic() >= deadline
                            ):
                                truncated = True
                                break

                            count += 1
                            try:
                                if entry.is_dir():
                                    stat = entry.stat()
                                    key = (stat.st_dev, stat.st_ino)
                                    # A symlink loop resolves to an inode that
                                    # has already been walked.
                                    if key in visited:
                                        continue
                                    visited.add(key)
                                    stack.append(entry.path)
                                elif entry.is_file():
                                    total_size += entry.stat().st_size
                                else:
                                    # Broken symlinks and special files.
                                    total_size += entry.stat(
                                        follow_symlinks=False
                                    ).st_size
                            except OSError:
                                unreadable += 1
                except OSError:
                    # The entry itself was counted; only its contents failed.
                    unreadable += 1

                if truncated:
                    break
        except Exception as exc:
            logger.exception("Folder scan failed for %s", self.folder_path)
            if not cancel_event.is_set():
                GLib.idle_add(self._on_scan_error, generation, str(exc))
            return

        if cancel_event.is_set():
            return

        self._idle_source_id = GLib.idle_add(
            self._on_scan_done,
            generation,
            count,
            total_size,
            unreadable,
            truncated,
        )

    def _on_scan_done(
        self,
        generation: int,
        count: int,
        total_size: int,
        unreadable: int,
        truncated: bool,
    ) -> bool:
        self._idle_source_id = None
        if self._cancelled or generation != self._generation:
            return GLib.SOURCE_REMOVE

        self._calculating = False
        self.item_count = count
        self._total_size = total_size
        self._unreadable = unreadable
        self._scan_truncated = truncated
        self._update_info_bar()
        self._notify_status_changed()
        return GLib.SOURCE_REMOVE

    def _on_scan_error(self, generation: int, error: str) -> bool:
        self._idle_source_id = None
        if self._cancelled or generation != self._generation:
            return GLib.SOURCE_REMOVE

        logger.warning("Folder scan error for %s: %s", self.folder_path, error)
        self._calculating = False
        self._scan_failed = True
        self._update_info_bar()
        self._notify_status_changed()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ state

    def _note_text(self) -> str:
        if self._scan_failed:
            return _("Could not calculate folder totals.")
        if self._unreadable and self._scan_truncated:
            return _(
                "{unreadable} entries could not be read; totals are partial "
                "because the scan reached its limit."
            ).format(unreadable=f"{self._unreadable:,}")
        if self._unreadable:
            return _("{unreadable} entries could not be read.").format(
                unreadable=f"{self._unreadable:,}"
            )
        if self._scan_truncated:
            return _("Totals are partial because the scan reached its limit.")
        if self._listing_truncated:
            return _("The listing is capped at {count} entries.").format(
                count=f"{LIST_SCAN_LIMIT:,}"
            )
        return ""

    def _update_info_bar(self) -> None:
        if self._read_error:
            self.lbl_info.set_text("")
            self.lbl_note.set_text("")
            return

        if self._calculating:
            self.lbl_info.set_text(_("Calculating..."))
            self.lbl_note.set_text("")
            return

        self.lbl_info.set_text(
            ngettext("{count} item", "{count} items", self.item_count).format(
                count=f"{self.item_count:,}"
            )
        )
        self.lbl_note.set_text(self._note_text())

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("Folder status callback failed")

    def set_status_callback(self, callback: Optional[StatusCallback]) -> None:
        """Register a callback invoked when the status metadata changes."""
        self._status_callback = callback if callable(callback) else None

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._read_error or self._scan_failed:
            return [
                (_("Items"), _("Unavailable")),
                (_("Size"), _("Unavailable")),
            ]

        if self._calculating:
            return [
                (_("Items"), _("Calculating...")),
                (_("Size"), _("Calculating...")),
            ]

        items = [
            (_("Items"), f"{self.item_count:,}"),
            (_("Size"), format_size(self._total_size)),
        ]
        if self._unreadable:
            items.append((_("Unreadable"), f"{self._unreadable:,}"))
        return items[:3]

    def teardown(self) -> None:
        """Cancel the scan and reject late idle callbacks from this instance."""
        self._cancelled = True
        self._generation += 1
        self._cancel_event.set()

        if self._idle_source_id is not None:
            try:
                GLib.source_remove(self._idle_source_id)
            except Exception:
                logger.debug("Folder scan idle source was already removed")
            self._idle_source_id = None

        self._status_callback = None
        self._scan_thread = None

    def get_desired_size(self, screen_w: int, screen_h: int):
        target_w = min(880, int(screen_w * 0.70))
        displayed_items = min(self.item_count, 25)
        item_h = 38
        content_h = 220 + displayed_items * item_h
        min_h = 360
        max_h = min(780, int(screen_h * 0.75))
        target_h = max(min_h, min(max_h, content_h))
        return target_w, target_h
