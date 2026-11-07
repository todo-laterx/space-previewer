"""Pure-Python, GTK-free file parsers with strict untrusted-input bounds.

All limits match ``SECURITY.md`` and ``CLAUDE.md`` section 5. This module must
never import ``gi`` or ``Gtk`` so unit tests, CLI tools, and alternative UIs
can exercise the parsers without a display server or GTK runtime.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import datetime
import re
import tarfile
from typing import Optional
import zipfile

from utils.formatters import format_date
from utils.i18n import _
from viewers.office_common import open_office_zip, read_xml

# ---------------------------------------------------------------------------
# Archive limits & parser (ZIP / TAR)
# ---------------------------------------------------------------------------

MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class ArchiveEncryptedError(Exception):
    """Raised when an archive contains encrypted entries."""


class ArchiveFormatError(Exception):
    """Raised when an archive format is unsupported or corrupted."""


@dataclass(frozen=True)
class ArchiveEntryData:
    name: str
    size: int
    is_dir: bool
    date_str: str


@dataclass(frozen=True)
class ArchivePreviewData:
    entries: list[ArchiveEntryData]
    total_uncompressed: int
    truncated: bool


def _zip_date(info: zipfile.ZipInfo) -> str:
    try:
        return format_date(datetime.datetime(*info.date_time).timestamp())
    except (ValueError, OverflowError, OSError):
        return ""


def _tar_date(member: tarfile.TarInfo) -> str:
    if not member.mtime:
        return ""
    try:
        return format_date(member.mtime)
    except (ValueError, OverflowError, OSError):
        return ""


def read_archive_entries(
    file_path: str,
    max_entries: int = MAX_ARCHIVE_ENTRIES,
    max_uncompressed_bytes: int = MAX_ARCHIVE_UNCOMPRESSED_BYTES,
) -> ArchivePreviewData:
    """List archive members without extracting any file data."""
    entries: list[ArchiveEntryData] = []
    total_uncompressed = 0
    truncated = False

    if zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, "r") as zf:
            for info in zf.infolist():
                if info.flag_bits & 0x1:
                    raise ArchiveEncryptedError(
                        _(
                            "This archive contains encrypted entries "
                            "and cannot be previewed."
                        )
                    )
                if len(entries) >= max_entries:
                    truncated = True
                    break
                if total_uncompressed + info.file_size > max_uncompressed_bytes:
                    truncated = True
                    break

                entries.append(
                    ArchiveEntryData(
                        name=info.filename,
                        size=info.file_size,
                        is_dir=info.is_dir(),
                        date_str=_zip_date(info),
                    )
                )
                total_uncompressed += info.file_size
        return ArchivePreviewData(entries, total_uncompressed, truncated)

    if tarfile.is_tarfile(file_path):
        with tarfile.open(file_path, "r:*") as tf:
            for member in tf:
                if len(entries) >= max_entries:
                    truncated = True
                    break
                if total_uncompressed + member.size > max_uncompressed_bytes:
                    truncated = True
                    break

                entries.append(
                    ArchiveEntryData(
                        name=member.name,
                        size=member.size,
                        is_dir=member.isdir(),
                        date_str=_tar_date(member),
                    )
                )
                total_uncompressed += member.size
        return ArchivePreviewData(entries, total_uncompressed, truncated)

    raise ArchiveFormatError(_("Unsupported archive format or corrupted file."))


# ---------------------------------------------------------------------------
# CSV / TSV limits & streaming parser
# ---------------------------------------------------------------------------

MAX_CSV_ROWS = 5000
MAX_CSV_COLUMNS = 100
SNIFF_BYTES = 4096


@dataclass(frozen=True)
class CSVPreviewData:
    headers: Optional[list[str]]
    rows: list[list[str]]
    truncated_rows: bool
    truncated_columns: bool


def read_csv_preview(
    file_path: str,
    max_rows: int = MAX_CSV_ROWS,
    max_columns: int = MAX_CSV_COLUMNS,
) -> CSVPreviewData:
    """Stream a bounded CSV/TSV table preview."""
    if file_path.lower().endswith((".tsv", ".tab")):
        delimiter = "\t"
    else:
        delimiter = ","

    headers: Optional[list[str]] = None
    data_rows: list[list[str]] = []
    truncated_rows = False
    truncated_columns = False

    with open(
        file_path, "r", encoding="utf-8", errors="replace", newline=""
    ) as handle:
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
                if len(row) > max_columns:
                    truncated_columns = True
                    headers = row[:max_columns]
                else:
                    headers = row
                continue

            if not row:
                continue

            if len(data_rows) >= max_rows:
                truncated_rows = True
                break

            if len(row) > max_columns:
                truncated_columns = True

            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            elif len(row) > len(headers):
                row = row[: len(headers)]

            data_rows.append(row)

    return CSVPreviewData(
        headers=headers,
        rows=data_rows,
        truncated_rows=truncated_rows,
        truncated_columns=truncated_columns,
    )


# ---------------------------------------------------------------------------
# Office Open XML parsers (.docx, .xlsx, .pptx)
# ---------------------------------------------------------------------------

MAX_XLSX_ROWS = 500
MAX_XLSX_COLS = 50


@dataclass(frozen=True)
class DocxRunData:
    text: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class DocxBlockData:
    kind: str  # "paragraph" or "table"
    runs: tuple[DocxRunData, ...] = ()
    table_text: str = ""


@dataclass(frozen=True)
class DocxPreviewData:
    blocks: list[DocxBlockData]
    paragraph_count: int
    word_count: int
    empty_body: bool = False


def read_docx_preview(file_path: str) -> DocxPreviewData:
    """Parse bounded paragraphs, runs, and tables from a .docx file."""
    with open_office_zip(file_path) as zf:
        root = read_xml(zf, "word/document.xml")

    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    body = root.find("w:body", namespaces)
    if body is None:
        return DocxPreviewData(blocks=[], paragraph_count=0, word_count=0, empty_body=True)

    blocks: list[DocxBlockData] = []
    p_count = 0
    word_count = 0

    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            p_count += 1
            p_style = None
            p_pr = child.find("w:pPr", namespaces)
            if p_pr is not None:
                p_style_elem = p_pr.find("w:pStyle", namespaces)
                if p_style_elem is not None:
                    val = p_style_elem.attrib.get(f"{{{namespaces['w']}}}val", "")
                    if "Heading1" in val or "heading 1" in val.lower():
                        p_style = "h1"
                    elif "Heading2" in val or "heading 2" in val.lower():
                        p_style = "h2"
                    elif "Heading3" in val or "heading 3" in val.lower():
                        p_style = "h3"

            run_items: list[DocxRunData] = []
            for r in child.findall("w:r", namespaces):
                r_pr = r.find("w:rPr", namespaces)
                is_bold = r_pr is not None and r_pr.find("w:b", namespaces) is not None
                is_italic = r_pr is not None and r_pr.find("w:i", namespaces) is not None

                t_elem = r.find("w:t", namespaces)
                if t_elem is not None and t_elem.text:
                    text = t_elem.text
                    word_count += len(text.split())
                    tags: list[str] = []
                    if p_style:
                        tags.append(p_style)
                    elif is_bold:
                        tags.append("bold")
                    if is_italic:
                        tags.append("italic")
                    run_items.append(DocxRunData(text=text, tags=tuple(tags)))

            blocks.append(DocxBlockData(kind="paragraph", runs=tuple(run_items)))

        elif tag == "tbl":
            rows = child.findall("w:tr", namespaces)
            table_data = []
            for row in rows:
                row_cells = []
                for cell in row.findall("w:tc", namespaces):
                    cell_text = "".join(cell.itertext()).strip()
                    row_cells.append(cell_text)
                table_data.append(row_cells)

            if table_data and table_data[0]:
                col_widths = [
                    max(len(row[i]) if i < len(row) else 0 for row in table_data)
                    for i in range(len(table_data[0]))
                ]
                col_widths = [max(w, 8) for w in col_widths]
                sep_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+\n"
                lines = [sep_line]
                for r_idx, row in enumerate(table_data):
                    line = "|"
                    for c_idx, w in enumerate(col_widths):
                        val = row[c_idx] if c_idx < len(row) else ""
                        line += f" {val.ljust(w)} |"
                    lines.append(line + "\n")
                    if r_idx == 0:
                        lines.append(sep_line)
                lines.append(sep_line + "\n")
                blocks.append(DocxBlockData(kind="table", table_text="".join(lines)))

    return DocxPreviewData(
        blocks=blocks,
        paragraph_count=p_count,
        word_count=word_count,
        empty_body=False,
    )


def col_to_index(col_str: str) -> int:
    """Convert Excel column letters like A, B, AA to 0-based index."""
    exp = 0
    idx = 0
    for char in reversed(col_str):
        idx += (ord(char.upper()) - ord("A") + 1) * (26 ** exp)
        exp += 1
    return idx - 1


def get_col_letter(n: int) -> str:
    """Convert 0-based column index to Excel column letters (A, B, ..., AA)."""
    result = ""
    while n >= 0:
        result = chr(n % 26 + 65) + result
        n = n // 26 - 1
    return result


@dataclass(frozen=True)
class XlsxPreviewData:
    sheet_count: int
    sheet_name: str
    col_names: list[str]
    data_rows: list[list[str]]
    row_count: int
    col_count: int
    no_sheets: bool = False


def read_xlsx_preview(
    file_path: str,
    max_rows: int = MAX_XLSX_ROWS,
    max_cols: int = MAX_XLSX_COLS,
) -> XlsxPreviewData:
    """Parse bounded sheet metadata and rows from an .xlsx file."""
    with open_office_zip(file_path) as zf:
        entries = zf.namelist()

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in entries:
            root_ss = read_xml(zf, "xl/sharedStrings.xml")
            for si in root_ss.findall(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"
            ):
                t_parts = [
                    t.text
                    for t in si.findall(
                        ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                    )
                    if t.text
                ]
                shared_strings.append("".join(t_parts))

        sheet_names: list[str] = []
        if "xl/workbook.xml" in entries:
            root_wb = read_xml(zf, "xl/workbook.xml")
            for s in root_wb.findall(
                ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            ):
                name = s.attrib.get("name")
                if not name:
                    name = _("Sheet %(number)s") % {"number": len(sheet_names) + 1}
                sheet_names.append(name)

        sheet_file = "xl/worksheets/sheet1.xml"
        if sheet_file not in entries:
            sheets = [
                f
                for f in entries
                if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")
            ]
            if sheets:
                sheet_file = sheets[0]
            else:
                return XlsxPreviewData(
                    sheet_count=len(sheet_names),
                    sheet_name=sheet_names[0] if sheet_names else "",
                    col_names=[],
                    data_rows=[],
                    row_count=0,
                    col_count=0,
                    no_sheets=True,
                )

        root_sheet = read_xml(zf, sheet_file)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        grid_data: list[dict[int, str]] = []
        detected_cols = 0

        for row_elem in root_sheet.findall(".//s:row", ns):
            if len(grid_data) >= max_rows:
                break

            row_dict: dict[int, str] = {}
            for c in row_elem.findall("s:c", ns):
                ref = c.attrib.get("r", "")
                match = re.match(r"([A-Za-z]+)([0-9]+)", ref)
                if not match:
                    continue
                c_idx = col_to_index(match.group(1))
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
                if c_idx + 1 > detected_cols:
                    detected_cols = c_idx + 1

            grid_data.append(row_dict)

        sheet_count = len(sheet_names) if sheet_names else 1
        sheet_name = (
            sheet_names[0]
            if sheet_names
            else _("Sheet %(number)s") % {"number": 1}
        )

        if not grid_data:
            return XlsxPreviewData(
                sheet_count=sheet_count,
                sheet_name=sheet_name,
                col_names=[],
                data_rows=[],
                row_count=0,
                col_count=0,
            )

        effective_cols = min(detected_cols, max_cols)
        full_rows = [
            [r_dict.get(c, "") for c in range(effective_cols)]
            for r_dict in grid_data
        ]
        headers = full_rows[0]
        data_rows = full_rows[1:]

        col_names = []
        for idx in range(effective_cols):
            h_val = headers[idx] if idx < len(headers) else ""
            letter = get_col_letter(idx)
            col_names.append(
                _("%(letter)s: %(header)s") % {"letter": letter, "header": h_val}
                if h_val.strip()
                else letter
            )

        return XlsxPreviewData(
            sheet_count=sheet_count,
            sheet_name=sheet_name,
            col_names=col_names,
            data_rows=data_rows,
            row_count=len(grid_data),
            col_count=effective_cols,
        )


@dataclass(frozen=True)
class PptxPreviewData:
    slides: list[list[str]]


def read_pptx_preview(file_path: str) -> PptxPreviewData:
    """Parse slide text paragraphs in slide-number order from a .pptx file."""
    with open_office_zip(file_path) as zf:
        slide_files = sorted(
            [
                f
                for f in zf.namelist()
                if f.startswith("ppt/slides/slide") and f.endswith(".xml")
            ],
            key=lambda x: int("".join(filter(str.isdigit, x)) or 0),
        )
        if not slide_files:
            return PptxPreviewData(slides=[])

        ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        }
        slides: list[list[str]] = []
        for s_file in slide_files:
            root_slide = read_xml(zf, s_file)
            text_paragraphs: list[str] = []
            for p in root_slide.findall(".//a:p", ns):
                t_parts = [t.text for t in p.findall(".//a:t", ns) if t.text]
                if t_parts:
                    line = "".join(t_parts).strip()
                    if line:
                        text_paragraphs.append(line)
            slides.append(text_paragraphs)

    return PptxPreviewData(slides=slides)


# ---------------------------------------------------------------------------
# Mermaid content detection
# ---------------------------------------------------------------------------

MERMAID_KEYWORDS = (
    "flowchart ",
    "flowchart\n",
    "graph ",
    "graph\n",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "gantt",
    "pie",
    "mindmap",
    "journey",
    "gitGraph",
    "timeline",
    "quadrantChart",
    "xychart-beta",
    "C4Context",
)


def is_mermaid_content(content: str) -> bool:
    """Detect whether raw text is a standalone Mermaid diagram."""
    stripped = content.lstrip()
    while stripped.startswith("%%"):
        newline_idx = stripped.find("\n")
        if newline_idx == -1:
            break
        stripped = stripped[newline_idx + 1 :].lstrip()
    return any(stripped.startswith(kw) for kw in MERMAID_KEYWORDS)
