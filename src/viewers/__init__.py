import logging
import os

from .image_viewer import ImageViewer
from .text_viewer import TextViewer
from .markdown_viewer import MarkdownViewer, is_mermaid_content
from .csv_viewer import CSVViewer
from .pdf_viewer import PDFViewer
from .media_viewer import MediaViewer
from .archive_viewer import ArchiveViewer
from .font_viewer import FontViewer
from .folder_viewer import FolderViewer
from .docx_viewer import DocxViewer
from .excel_viewer import ExcelViewer
from .pptx_viewer import PptxViewer
from .html_viewer import HtmlViewer
from .registry import find_plugin
from utils.mime_detector import detect_mime_type
from utils.formatters import format_size, format_date
from utils.i18n import _

logger = logging.getLogger(__name__)

def create_viewer_for_file(file_path: str):
    """Factory function to instantiate the proper viewer widget for a file path."""
    if not os.path.exists(file_path):
        from gi.repository import Gtk
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Gtk.Label(label=_("File not found: %s") % file_path))
        return box

    if os.path.isdir(file_path):
        return FolderViewer(file_path)

    mime = detect_mime_type(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    plugin_viewer = find_plugin(file_path, mime, ext)
    if plugin_viewer is not None:
        return plugin_viewer

    # HTML (before the generic text/ branch)
    if ext in (".html", ".htm", ".xhtml") or mime in ("text/html", "application/xhtml+xml"):
        return HtmlViewer(file_path)

    # Images
    if mime.startswith("image/"):
        return ImageViewer(file_path)

    # PDF
    if mime == "application/pdf" or ext == ".pdf":
        return PDFViewer(file_path)

    # Word Documents
    if ext in [".docx", ".doc"] or mime in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword"
    ]:
        return DocxViewer(file_path)

    # Excel Spreadsheets
    if ext in [".xlsx", ".xls"] or mime in [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
    ]:
        return ExcelViewer(file_path)

    # PowerPoint Presentations
    if ext in [".pptx", ".ppt"] or mime in [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint"
    ]:
        return PptxViewer(file_path)

    # CSV / TSV
    if ext in [".csv", ".tsv"] or mime in ["text/csv", "text/tab-separated-values"]:
        return CSVViewer(file_path)

    # Video & Audio
    if mime.startswith("video/"):
        return MediaViewer(file_path, is_audio=False)
    if mime.startswith("audio/"):
        return MediaViewer(file_path, is_audio=True)

    # Archives
    if ext in [".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".tar.gz", ".tar.bz2", ".tar.xz"] or mime in [
        "application/zip", "application/x-tar", "application/gzip", "application/x-bzip2", "application/x-xz"
    ]:
        return ArchiveViewer(file_path)

    # Fonts
    if ext in [".ttf", ".otf", ".woff", ".woff2"] or mime.startswith("font/"):
        return FontViewer(file_path)

    # Markdown & Mermaid (open directly in rich Preview mode)
    if ext in [".md", ".markdown", ".mdown", ".mkd", ".mdx", ".mmd", ".mermaid"] or mime in [
        "text/markdown", "text/vnd.mermaid"
    ]:
        return MarkdownViewer(file_path)

    # Text / Code
    if mime.startswith("text/") or mime in [
        "application/json", "application/javascript", "application/x-sh", "application/xml", "application/x-python"
    ]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(8192)
            if is_mermaid_content(sample) or "```mermaid" in sample:
                return MarkdownViewer(file_path)
        except Exception:
            logger.debug("Could not sniff text content in %s", file_path, exc_info=True)
        return TextViewer(file_path)

    # Fallback to MarkdownViewer / TextViewer if readable, else info
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)
            if b"\0" not in chunk:
                sample = chunk.decode("utf-8", errors="ignore")
                if is_mermaid_content(sample) or "```mermaid" in sample:
                    return MarkdownViewer(file_path)
                return TextViewer(file_path)
    except Exception:
        logger.debug("Could not sniff binary content in %s", file_path, exc_info=True)

    # Generic binary file info
    from gi.repository import Gtk

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    box.set_margin_top(48)
    box.set_margin_bottom(48)

    icon = Gtk.Image.new_from_icon_name("application-x-generic")
    icon.set_pixel_size(96)
    box.append(icon)

    name_lbl = Gtk.Label(label=os.path.basename(file_path))
    name_lbl.add_css_class("title-2")
    box.append(name_lbl)

    size = os.path.getsize(file_path)
    mtime = os.path.getmtime(file_path)
    details = Gtk.Label(
        label=_("Type: %(mime)s\nSize: %(size)s\nModified: %(date)s")
        % {
            "mime": mime,
            "size": format_size(size),
            "date": format_date(mtime),
        }
    )
    details.add_css_class("dim-label")
    box.append(details)

    return box
