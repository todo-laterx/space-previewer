import logging
import os
import re

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango

from utils.formatters import format_size
from utils.i18n import _, ngettext
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
            with open_office_zip(self.file_path) as zf:
                root = read_xml(zf, "word/document.xml")

            namespaces = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }

            p_count = 0
            word_count = 0

            # Traverse body
            body = root.find("w:body", namespaces)
            if body is None:
                self.buffer.set_text(_("Document body is empty."))
                self._update_info()
                return

            for child in body:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

                if tag == "p":
                    p_count += 1
                    # Check paragraph style (heading etc)
                    p_style = None
                    pPr = child.find("w:pPr", namespaces)
                    if pPr is not None:
                        pStyle_elem = pPr.find("w:pStyle", namespaces)
                        if pStyle_elem is not None:
                            val = pStyle_elem.attrib.get(f"{{{namespaces['w']}}}val", "")
                            if "Heading1" in val or "heading 1" in val.lower():
                                p_style = "h1"
                            elif "Heading2" in val or "heading 2" in val.lower():
                                p_style = "h2"
                            elif "Heading3" in val or "heading 3" in val.lower():
                                p_style = "h3"

                    # Collect runs
                    runs = child.findall("w:r", namespaces)
                    for r in runs:
                        rPr = r.find("w:rPr", namespaces)
                        is_bold = rPr is not None and rPr.find("w:b", namespaces) is not None
                        is_italic = rPr is not None and rPr.find("w:i", namespaces) is not None

                        t_elem = r.find("w:t", namespaces)
                        if t_elem is not None and t_elem.text:
                            text = t_elem.text
                            word_count += len(text.split())
                            iter_end = self.buffer.get_end_iter()

                            tags = []
                            if p_style:
                                tags.append(p_style)
                            elif is_bold:
                                tags.append("bold")
                            if is_italic:
                                tags.append("italic")

                            if tags:
                                for tname in tags:
                                    self.buffer.insert_with_tags_by_name(iter_end, text, tname)
                            else:
                                self.buffer.insert(iter_end, text)

                    iter_end = self.buffer.get_end_iter()
                    self.buffer.insert(iter_end, "\n\n")

                elif tag == "tbl":
                    # Table parsing
                    iter_end = self.buffer.get_end_iter()
                    self.buffer.insert(iter_end, "\n")
                    rows = child.findall("w:tr", namespaces)
                    table_data = []
                    for row in rows:
                        row_cells = []
                        for cell in row.findall("w:tc", namespaces):
                            cell_text = "".join(cell.itertext()).strip()
                            row_cells.append(cell_text)
                        table_data.append(row_cells)

                    if table_data:
                        col_widths = [max(len(row[i]) if i < len(row) else 0 for row in table_data) for i in range(len(table_data[0]))]
                        col_widths = [max(w, 8) for w in col_widths]
                        sep_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+\n"
                        self.buffer.insert_with_tags_by_name(iter_end, sep_line, "table")
                        for r_idx, row in enumerate(table_data):
                            line = "|"
                            for c_idx, w in enumerate(col_widths):
                                val = row[c_idx] if c_idx < len(row) else ""
                                line += f" {val.ljust(w)} |"
                            line += "\n"
                            iter_end = self.buffer.get_end_iter()
                            self.buffer.insert_with_tags_by_name(iter_end, line, "table")
                            if r_idx == 0:
                                iter_end = self.buffer.get_end_iter()
                                self.buffer.insert_with_tags_by_name(iter_end, sep_line, "table")
                        iter_end = self.buffer.get_end_iter()
                        self.buffer.insert_with_tags_by_name(iter_end, sep_line + "\n", "table")

            self._paragraph_count = p_count
            self._word_count = word_count
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
