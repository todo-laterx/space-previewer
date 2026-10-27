import logging
import os

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from utils.formatters import format_size
from utils.i18n import _, ngettext
from viewers.office_common import OfficeParseError, open_office_zip, read_xml

log = logging.getLogger(__name__)

class PptxViewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self._slide_count = 0
        try:
            self._size_bytes = os.path.getsize(file_path)
        except OSError:
            self._size_bytes = 0

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
            with open_office_zip(self.file_path) as zf:
                slide_files = sorted(
                    [f for f in zf.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")],
                    key=lambda x: int("".join(filter(str.isdigit, x)) or 0)
                )

                if not slide_files:
                    self._update_info()
                    self.slides_box.append(Gtk.Label(label=_("No slides found in PowerPoint presentation.")))
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

                    header_badge = Gtk.Label(
                        label=_("SLIDE %(number)s") % {"number": s_idx + 1}
                    )
                    header_badge.add_css_class("caption")
                    header_badge.add_css_class("dim-label")
                    header_badge.set_halign(Gtk.Align.START)
                    header_badge.set_margin_start(16)
                    header_badge.set_margin_top(12)
                    card.append(header_badge)

                    root_slide = read_xml(zf, s_file)

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
                            line_lbl = Gtk.Label(
                                label=_("•  %(text)s") % {"text": body_line}
                            )
                            line_lbl.set_halign(Gtk.Align.START)
                            line_lbl.set_wrap(True)
                            line_lbl.set_margin_start(24)
                            line_lbl.set_margin_end(16)
                            line_lbl.set_margin_bottom(4)
                            card.append(line_lbl)
                    else:
                        empty_lbl = Gtk.Label(label=_("(Visual or graphical slide content)"))
                        empty_lbl.add_css_class("dim-label")
                        empty_lbl.set_halign(Gtk.Align.START)
                        empty_lbl.set_margin_start(16)
                        empty_lbl.set_margin_bottom(12)
                        card.append(empty_lbl)

                    self.slides_box.append(card)

                self._slide_count = len(slide_files)
                self._update_info()

        except OfficeParseError as exc:
            self.slides_box.append(Gtk.Label(
                label=_("Could not load PowerPoint presentation:\n%(error)s")
                % {"error": str(exc)}
            ))
        except Exception:
            log.exception("Could not load PowerPoint presentation %s", self.file_path)
            self.slides_box.append(Gtk.Label(
                label=_("Could not load PowerPoint presentation.")
            ))

    def _update_info(self) -> None:
        slides = ngettext(
            "{count} slide", "{count} slides", self._slide_count
        ).format(count=f"{self._slide_count:,}")
        self.lbl_info.set_text(
            _("PowerPoint (.pptx) • %(slides)s • %(size)s")
            % {"slides": slides, "size": format_size(self._size_bytes)}
        )

    def get_status_items(self) -> list[tuple[str, str]]:
        size_item = (_("Size"), format_size(self._size_bytes))
        # A legacy .ppt body is not parsed, so report only its size.
        if os.path.splitext(self.file_path)[1].lower() != ".pptx":
            return [size_item]
        return [(_("Slides"), f"{self._slide_count:,}"), size_item]

    def teardown(self) -> None:
        """The viewer owns no external resources."""
