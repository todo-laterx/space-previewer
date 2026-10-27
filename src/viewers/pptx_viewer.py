import os
import io
import zipfile
import xml.etree.ElementTree as ET
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango

from utils.formatters import format_size

class PptxViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_hexpand(True)
        self.scrolled.set_vexpand(True)
        self.append(self.scrolled)

        self.slides_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.slides_box.set_margin_start(32)
        self.slides_box.set_margin_end(32)
        self.slides_box.set_margin_top(24)
        self.slides_box.set_margin_bottom(24)
        self.scrolled.set_child(self.slides_box)

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

        self.load_pptx()

    def load_pptx(self):
        try:
            with open(self.file_path, "rb") as f:
                raw_bytes = f.read(50 * 1024 * 1024)
            with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                slide_files = sorted(
                    [f for f in zf.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")],
                    key=lambda x: int("".join(filter(str.isdigit, x)) or 0)
                )

                if not slide_files:
                    self.slides_box.append(Gtk.Label(label="No slides found in PowerPoint presentation."))
                    return

                ns = {
                    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                    "p": "http://schemas.openxmlformats.org/presentationml/2006/main"
                }

                for s_idx, s_file in enumerate(slide_files):
                    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                    card.add_css_class("card")
                    card.set_margin_top(4)
                    card.set_margin_bottom(4)

                    header_badge = Gtk.Label(label=f"SLIDE {s_idx + 1}")
                    header_badge.add_css_class("caption")
                    header_badge.add_css_class("dim-label")
                    header_badge.set_halign(Gtk.Align.START)
                    header_badge.set_margin_start(16)
                    header_badge.set_margin_top(12)
                    card.append(header_badge)

                    slide_xml = zf.read(s_file)
                    root_slide = ET.fromstring(slide_xml)

                    text_paragraphs = []
                    for p in root_slide.findall(".//a:p", ns):
                        t_parts = [t.text for t in p.findall(".//a:t", ns) if t.text]
                        if t_parts:
                            line = "".join(t_parts).strip()
                            if line:
                                text_paragraphs.append(line)

                    if text_paragraphs:
                        # First paragraph can be title
                        title_lbl = Gtk.Label(label=text_paragraphs[0])
                        title_lbl.add_css_class("title-3")
                        title_lbl.set_halign(Gtk.Align.START)
                        title_lbl.set_wrap(True)
                        title_lbl.set_margin_start(16)
                        title_lbl.set_margin_end(16)
                        card.append(title_lbl)

                        for body_line in text_paragraphs[1:]:
                            line_lbl = Gtk.Label(label=f"•  {body_line}")
                            line_lbl.set_halign(Gtk.Align.START)
                            line_lbl.set_wrap(True)
                            line_lbl.set_margin_start(24)
                            line_lbl.set_margin_end(16)
                            line_lbl.set_margin_bottom(4)
                            card.append(line_lbl)
                    else:
                        empty_lbl = Gtk.Label(label="(Visual or graphical slide content)")
                        empty_lbl.add_css_class("dim-label")
                        empty_lbl.set_halign(Gtk.Align.START)
                        empty_lbl.set_margin_start(16)
                        empty_lbl.set_margin_bottom(12)
                        card.append(empty_lbl)

                    self.slides_box.append(card)

                size = os.path.getsize(self.file_path)
                self.lbl_info.set_text(f"PowerPoint (.pptx) • {len(slide_files)} slides • {format_size(size)}")

        except Exception as e:
            self.slides_box.append(Gtk.Label(label=f"Could not load PowerPoint presentation:\n{e}"))
