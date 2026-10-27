import os
import io
import zipfile
import xml.etree.ElementTree as ET
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango

from utils.formatters import format_size

class DocxViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path

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
            with open(self.file_path, "rb") as f:
                raw_bytes = f.read(50 * 1024 * 1024)
            with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                xml_content = zf.read("word/document.xml")

            root = ET.fromstring(xml_content)
            namespaces = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }

            p_count = 0
            word_count = 0

            # Traverse body
            body = root.find("w:body", namespaces)
            if body is None:
                self.buffer.set_text("Document body is empty.")
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

            size = os.path.getsize(self.file_path)
            self.lbl_info.set_text(f"Word Document (.docx) • {p_count:,} paragraphs • {word_count:,} words • {format_size(size)}")

        except Exception as e:
            self.buffer.set_text(f"Could not load Word document:\n{e}")

    def load_legacy_doc(self):
        try:
            # For legacy .doc, extract readable strings
            with open(self.file_path, "rb") as f:
                raw = f.read(5 * 1024 * 1024)
            # Filter printable strings
            import re
            strings = re.findall(b'[\x20-\x7E\r\n\t]{4,}', raw)
            decoded = "\n".join(s.decode('latin-1', errors='ignore') for s in strings[:1000])
            self.buffer.set_text(decoded if decoded else "Legacy .doc file (binary format)")
            size = os.path.getsize(self.file_path)
            self.lbl_info.set_text(f"Legacy Word Document (.doc) • {format_size(size)}")
        except Exception as e:
            self.buffer.set_text(f"Could not load .doc file:\n{e}")
