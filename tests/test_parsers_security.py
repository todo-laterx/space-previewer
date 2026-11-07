import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils.parsers import (
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    MAX_CSV_COLUMNS,
    MAX_CSV_ROWS,
    MAX_XLSX_COLS,
    MAX_XLSX_ROWS,
    ArchiveEncryptedError,
    ArchiveFormatError,
    col_to_index,
    get_col_letter,
    is_mermaid_content,
    read_archive_entries,
    read_csv_preview,
    read_docx_preview,
    read_pptx_preview,
    read_xlsx_preview,
)
from viewers.office_common import (
    MAX_ENTRIES,
    MAX_ENTRY_BYTES,
    MAX_TOTAL_BYTES,
    OfficeParseError,
    open_office_zip,
    read_xml,
)


class HeadlessImportTest(unittest.TestCase):
    def test_parsers_and_office_common_import_without_gtk(self):
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(SRC)!r}); "
            "import utils.parsers, viewers.office_common; "
            "assert 'gi.repository.Gtk' not in sys.modules, list(sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class ArchiveParserSecurityTest(unittest.TestCase):
    def test_documented_archive_security_constants(self):
        self.assertEqual(MAX_ARCHIVE_ENTRIES, 5000)
        self.assertEqual(MAX_ARCHIVE_UNCOMPRESSED_BYTES, 200 * 1024 * 1024)

    def test_zip_listing_and_entry_limit_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "sample.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.mkdir("docs/")
                for idx in range(5):
                    zf.writestr(f"docs/file_{idx}.txt", f"hello-{idx}")

            full = read_archive_entries(archive_path)
            self.assertFalse(full.truncated)
            self.assertEqual(sum(1 for e in full.entries if e.is_dir), 1)
            self.assertEqual(sum(1 for e in full.entries if not e.is_dir), 5)

            capped = read_archive_entries(archive_path, max_entries=3)
            self.assertTrue(capped.truncated)
            self.assertEqual(len(capped.entries), 3)

    def test_tar_uncompressed_bytes_limit_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "sample.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tf:
                for idx in range(4):
                    payload = b"x" * 100
                    info = tarfile.TarInfo(name=f"item_{idx}.bin")
                    info.size = len(payload)
                    tf.addfile(info, io.BytesIO(payload))

            preview = read_archive_entries(
                archive_path,
                max_entries=100,
                max_uncompressed_bytes=250,
            )
            self.assertTrue(preview.truncated)
            self.assertEqual(len(preview.entries), 2)
            self.assertEqual(preview.total_uncompressed, 200)

    def test_encrypted_zip_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "secret.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("secret.txt", "classified")

            real_infolist = zipfile.ZipFile.infolist

            def fake_infolist(zf_self):
                infos = real_infolist(zf_self)
                infos[0].flag_bits |= 0x1
                return infos

            with mock.patch.object(zipfile.ZipFile, "infolist", fake_infolist):
                with self.assertRaises(ArchiveEncryptedError):
                    read_archive_entries(archive_path)

    def test_unsupported_archive_extension_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "sample.rar")
            Path(bad_path).write_bytes(b"not-an-archive")
            with self.assertRaises(ArchiveFormatError):
                read_archive_entries(bad_path)


class CsvParserSecurityTest(unittest.TestCase):
    def test_documented_csv_security_constants(self):
        self.assertEqual(MAX_CSV_ROWS, 5000)
        self.assertEqual(MAX_CSV_COLUMNS, 100)

    def test_csv_delimiter_detection_and_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            semi_path = os.path.join(tmp, "semi.csv")
            Path(semi_path).write_text("col1;col2;col3\na;b;c\nd;e;f\n", encoding="utf-8")
            semi_preview = read_csv_preview(semi_path)
            self.assertEqual(semi_preview.headers, ["col1", "col2", "col3"])
            self.assertEqual(semi_preview.rows, [["a", "b", "c"], ["d", "e", "f"]])

            csv_path = os.path.join(tmp, "table.csv")
            Path(csv_path).write_text("col1,col2,col3\na,b\nc,d,e,f\n", encoding="utf-8")

            preview = read_csv_preview(csv_path)
            self.assertEqual(preview.headers, ["col1", "col2", "col3"])
            self.assertEqual(preview.rows, [["a", "b", ""], ["c", "d", "e"]])
            self.assertFalse(preview.truncated_rows)
            self.assertFalse(preview.truncated_columns)

    def test_csv_row_and_column_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "large.csv")
            header = ",".join(f"h{i}" for i in range(6))
            rows = [",".join(f"r{r}c{c}" for c in range(6)) for r in range(5)]
            Path(csv_path).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")

            preview = read_csv_preview(csv_path, max_rows=3, max_columns=4)
            self.assertTrue(preview.truncated_rows)
            self.assertTrue(preview.truncated_columns)
            self.assertEqual(preview.headers, ["h0", "h1", "h2", "h3"])
            self.assertEqual(len(preview.rows), 3)
            self.assertTrue(all(len(r) == 4 for r in preview.rows))


class OfficeSecurityAndParsersTest(unittest.TestCase):
    def test_documented_office_security_constants(self):
        self.assertEqual(MAX_ENTRIES, 2000)
        self.assertEqual(MAX_ENTRY_BYTES, 20 * 1024 * 1024)
        self.assertEqual(MAX_TOTAL_BYTES, 100 * 1024 * 1024)
        self.assertEqual(MAX_XLSX_ROWS, 500)
        self.assertEqual(MAX_XLSX_COLS, 50)

    def test_office_zip_rejects_excessive_entries_and_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "doc.docx")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("word/document.xml", "<w:document/>")

            total_info = zipfile.ZipInfo("word/document.xml")
            total_info.file_size = MAX_TOTAL_BYTES + 1
            with mock.patch.object(zipfile.ZipFile, "infolist", return_value=[total_info]):
                with self.assertRaises(OfficeParseError):
                    open_office_zip(archive_path)

            many_infos = [zipfile.ZipInfo(f"f_{i}.xml") for i in range(MAX_ENTRIES + 1)]
            with mock.patch.object(zipfile.ZipFile, "infolist", return_value=many_infos):
                with self.assertRaises(OfficeParseError):
                    open_office_zip(archive_path)

            entry_info = zipfile.ZipInfo("word/document.xml")
            entry_info.file_size = MAX_ENTRY_BYTES + 1
            with open_office_zip(archive_path) as zf:
                with mock.patch.object(zf, "getinfo", return_value=entry_info):
                    with self.assertRaises(OfficeParseError):
                        read_xml(zf, "word/document.xml")

    def test_office_xml_rejects_doctype_and_entity_in_utf8_and_utf16(self):
        with tempfile.TemporaryDirectory() as tmp:
            utf8_bomb = os.path.join(tmp, "xxe_utf8.docx")
            with zipfile.ZipFile(utf8_bomb, "w") as zf:
                zf.writestr(
                    "word/document.xml",
                    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "bar">]><foo/>',
                )
            with open_office_zip(utf8_bomb) as zf:
                with self.assertRaises(OfficeParseError):
                    read_xml(zf, "word/document.xml")

            utf16_bomb = os.path.join(tmp, "xxe_utf16.docx")
            with zipfile.ZipFile(utf16_bomb, "w") as zf:
                zf.writestr(
                    "word/document.xml",
                    '<?xml version="1.0"?><!ENTITY boom "x"><foo/>'.encode("utf-16"),
                )
            with open_office_zip(utf16_bomb) as zf:
                with self.assertRaises(OfficeParseError):
                    read_xml(zf, "word/document.xml")

    def test_docx_xlsx_pptx_and_mermaid_parsers(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = os.path.join(tmp, "sample.docx")
            with zipfile.ZipFile(docx_path, "w") as zf:
                zf.writestr(
                    "word/document.xml",
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body>"
                    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                    "<w:r><w:t>Hello Docx</w:t></w:r></w:p>"
                    "</w:body></w:document>",
                )
            docx_preview = read_docx_preview(docx_path)
            self.assertEqual(docx_preview.paragraph_count, 1)
            self.assertEqual(docx_preview.word_count, 2)
            self.assertEqual(docx_preview.blocks[0].runs[0].tags, ("h1",))

            xlsx_path = os.path.join(tmp, "sample.xlsx")
            with zipfile.ZipFile(xlsx_path, "w") as zf:
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<si><t>Item</t></si></sst>",
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<sheetData>"
                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></row>'
                    '<row r="2"><c r="A2" t="s"><v>0</v></c><c r="B2"><v>99</v></c></row>'
                    "</sheetData></worksheet>",
                )
            xlsx_preview = read_xlsx_preview(xlsx_path)
            self.assertEqual(xlsx_preview.col_names, ["A: Item", "B: 42"])
            self.assertEqual(xlsx_preview.data_rows, [["Item", "99"]])
            self.assertEqual(col_to_index("AA"), 26)
            self.assertEqual(get_col_letter(26), "AA")

            pptx_path = os.path.join(tmp, "sample.pptx")
            with zipfile.ZipFile(pptx_path, "w") as zf:
                zf.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    "<p:cSld><p:spTree><p:sp><p:txBody>"
                    "<a:p><a:r><a:t>Slide Title</a:t></a:r></a:p>"
                    "<a:p><a:r><a:t>Bullet Point</a:t></a:r></a:p>"
                    "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
                )
            pptx_preview = read_pptx_preview(pptx_path)
            self.assertEqual(pptx_preview.slides, [["Slide Title", "Bullet Point"]])

            self.assertTrue(is_mermaid_content("%%{init: {}}%%\nflowchart TD\nA-->B"))
            self.assertFalse(is_mermaid_content("# Regular Markdown"))


if __name__ == "__main__":
    unittest.main()
