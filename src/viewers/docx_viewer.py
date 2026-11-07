import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango

from utils.formatters import format_size
from utils.i18n import _, ngettext
from utils.parsers import read_docx_preview
from viewers.office_common import OfficeParseError, open_office_zip, read_xml

log = logging.getLogger(__name__)

class DocxViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self._paragraph_count = 0
        self._word_count = 0
        try:
            self._size_bytes = os.path.getsize(file_path)
        except OSError:
            self._size_bytes = 0

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(40)
        self.text_view.set_right_margin(40)
        self.text_view.set_top_margin(28)
        self.text_view.set_bottom_margin(28)

        self.buffer = self.text_view.get_buffer()
        self.setup_tags()
        self.scrolled.set_child(self.text_view)

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

        self.load_document()

    def setup_tags(self):
        tag_table = self.buffer.get_tag_table()

        t_h1 = Gtk.TextTag.new("h1")
        t_h1.set_property("scale", 1.8)
        t_h1.set_property("weight", Pango.Weight.BOLD)
        t_h1.set_property("pixels-above-lines", 14)
        t_h1.set_property("pixels-below-lines", 8)
        tag_table.add(t_h1)

        t_h2 = Gtk.TextTag.new("h2")
        t_h2.set_property("scale", 1.4)
        t_h2.set_property("weight", Pango.Weight.BOLD)
        t_h2.set_property("pixels-above-lines", 10)
        t_h2.set_property("pixels-below-lines", 6)
        tag_table.add(t_h2)

        t_h3 = Gtk.TextTag.new("h3")
        t_h3.set_property("scale", 1.2)
        t_h3.set_property("weight", Pango.Weight.BOLD)
        t_h3.set_property("pixels-above-lines", 8)
        t_h3.set_property("pixels-below-lines", 4)
        tag_table.add(t_h3)

        t_bold = Gtk.TextTag.new("bold")
        t_bold.set_property("weight", Pango.Weight.BOLD)
        tag_table.add(t_bold)

        t_italic = Gtk.TextTag.new("italic")
        t_italic.set_property("style", Pango.Style.ITALIC)
        tag_table.add(t_italic)

        t_table = Gtk.TextTag.new("table")
        t_table.set_property("family", "monospace")
        tag_table.add(t_table)

    def load_document(self):
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == ".docx":
            self.load_docx()
        else:
            self.load_legacy_doc()

    def load_docx(self):
        try:
            preview = read_docx_preview(self.file_path)
            if preview.empty_body:
                self.buffer.set_text(_("Document body is empty."))
                self._update_info()
                return

            for block in preview.blocks:
                if block.kind == "paragraph":
                    for run in block.runs:
                        iter_end = self.buffer.get_end_iter()
                        if run.tags:
                            for tname in run.tags:
                                self.buffer.insert_with_tags_by_name(
                                    iter_end, run.text, tname
                                )
                        else:
                            self.buffer.insert(iter_end, run.text)
                    iter_end = self.buffer.get_end_iter()
                    self.buffer.insert(iter_end, "\n\n")
                elif block.kind == "table" and block.table_text:
                    iter_end = self.buffer.get_end_iter()
                    self.buffer.insert(iter_end, "\n")
                    iter_end = self.buffer.get_end_iter()
                    self.buffer.insert_with_tags_by_name(
                        iter_end, block.table_text, "table"
                    )

            self._paragraph_count = preview.paragraph_count
            self._word_count = preview.word_count
            self._update_info()

        except OfficeParseError as exc:
            self.buffer.set_text(
                _("Could not load Word document:\n%(error)s")
                % {"error": str(exc)}
            )
        except Exception:
            log.exception("Could not load Word document %s", self.file_path)
            self.buffer.set_text(_("Could not load Word document."))

    def load_legacy_doc(self):
        try:
            # For legacy .doc, extract readable strings
            with open(self.file_path, "rb") as f:
                raw = f.read(5 * 1024 * 1024)
            # Filter printable strings
            strings = re.findall(b'[\x20-\x7E\r\n\t]{4,}', raw)
            decoded = "\n".join(s.decode('latin-1', errors='ignore') for s in strings[:1000])
            self.buffer.set_text(decoded if decoded else _("Legacy .doc file (binary format)"))
            self.lbl_info.set_text(
                _("Legacy Word Document (.doc) • %(size)s")
                % {"size": format_size(self._size_bytes)}
            )
        except OSError:
            log.exception("Could not read .doc file %s", self.file_path)
            self.buffer.set_text(_("Could not load .doc file."))
        except Exception:
            log.exception("Could not parse .doc file %s", self.file_path)
            self.buffer.set_text(_("Could not load .doc file."))

    def _update_info(self) -> None:
        paragraphs = ngettext(
            "{count} paragraph", "{count} paragraphs", self._paragraph_count
        ).format(count=f"{self._paragraph_count:,}")
        words = ngettext(
            "{count} word", "{count} words", self._word_count
        ).format(count=f"{self._word_count:,}")
        self.lbl_info.set_text(
            _("%(type)s • %(paragraphs)s • %(words)s • %(size)s")
            % {
                "type": _("Word Document (.docx)"),
                "paragraphs": paragraphs,
                "words": words,
                "size": format_size(self._size_bytes),
            }
        )

    def get_status_items(self) -> list[tuple[str, str]]:
        size_item = (_("Size"), format_size(self._size_bytes))
        # A legacy .doc body is not parsed, so do not claim zero paragraphs
        # and words for it.
        if os.path.splitext(self.file_path)[1].lower() != ".docx":
            return [size_item]
        return [
            (_("Paragraphs"), f"{self._paragraph_count:,}"),
            (_("Words"), f"{self._word_count:,}"),
            size_item,
        ]

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        return (
            min(1040, int(screen_w * 0.85)),
            min(860, int(screen_h * 0.82)),
        )

    def teardown(self) -> None:
        """The viewer owns no external resources."""
