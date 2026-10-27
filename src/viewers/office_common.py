"""Bounded, dependency-free helpers for Office Open XML previews.

DOCX, XLSX and PPTX files are ZIP containers holding XML. All three viewers
share the limits below so a malformed or hostile document cannot exhaust
memory or trigger XML entity expansion. The caps match ``CLAUDE.md`` section 5
and ``SECURITY.md``.

This module must stay importable without GTK: the parsing tests exercise it
directly. Only the standard library and :mod:`utils.i18n` are imported.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
import zlib

from utils.i18n import _

# Untrusted-input caps for the ZIP container inside docx/xlsx/pptx files.
MAX_ENTRY_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 2000

# XML entity declarations enable entity-expansion ("billion laughs") attacks.
# Office XML never needs a DTD, so reject it before handing bytes to ElementTree.
_FORBIDDEN_XML_MARKERS = (b"<!doctype", b"<!entity")

_READ_ERRORS = (
    zipfile.BadZipFile,
    RuntimeError,
    NotImplementedError,
    OSError,
    EOFError,
    ValueError,
    zlib.error,
)


class OfficeParseError(Exception):
    """A user-safe, translated error raised while parsing an Office file.

    The message is already translated and suitable for display; viewers must
    not append raw exception text from the underlying parser.
    """


def _missing_part() -> OfficeParseError:
    return OfficeParseError(_("A required part of this Office document is missing."))


def _part_too_large() -> OfficeParseError:
    return OfficeParseError(
        _("A part of this Office document is too large to preview.")
    )


def _unreadable() -> OfficeParseError:
    return OfficeParseError(_("This Office document could not be read."))


def _entry_info(zf: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
    try:
        return zf.getinfo(name)
    except KeyError as exc:
        raise _missing_part() from exc


def open_office_zip(path: str) -> zipfile.ZipFile:
    """Open and validate an Office ZIP container.

    Raises :class:`OfficeParseError` when the file is not a ZIP, contains
    encrypted entries, has more than :data:`MAX_ENTRIES` entries, or declares
    more than :data:`MAX_TOTAL_BYTES` uncompressed bytes. The caller owns the
    returned handle and should use it as a context manager.
    """
    try:
        zf = zipfile.ZipFile(path, "r")
    except _READ_ERRORS as exc:
        raise OfficeParseError(_("This is not a valid Office document.")) from exc

    try:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise OfficeParseError(
                _("This Office document has too many parts to preview.")
            )

        total_bytes = 0
        for info in infos:
            # General-purpose bit 0 marks an encrypted entry. zipfile can read
            # it only with a password, which a preview never has.
            if info.flag_bits & 0x1:
                raise OfficeParseError(
                    _("Encrypted Office documents are not supported.")
                )
            total_bytes += info.file_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise OfficeParseError(
                    _("This Office document is too large to preview.")
                )
    except BaseException:
        zf.close()
        raise

    return zf


def read_text_entry(
    zf: zipfile.ZipFile, name: str, limit: int = MAX_ENTRY_BYTES
) -> bytes:
    """Read ``name`` with a hard byte budget.

    ``limit`` may lower the absolute per-entry cap but never raise it. An entry
    whose declared size exceeds the effective limit is rejected instead of
    being silently truncated, because truncated XML is not parseable.
    """
    info = _entry_info(zf, name)
    if info.file_size > MAX_ENTRY_BYTES:
        raise _part_too_large()

    effective_limit = min(max(int(limit), 0), MAX_ENTRY_BYTES)
    if info.file_size > effective_limit:
        raise _part_too_large()

    try:
        with zf.open(info, "r") as handle:
            # Read one extra byte to detect a central directory that lies
            # about the uncompressed size.
            data = handle.read(effective_limit + 1)
    except _READ_ERRORS as exc:
        raise _unreadable() from exc

    if len(data) > effective_limit:
        raise _part_too_large()
    return data


def _contains_forbidden_xml(data: bytes) -> bool:
    """Return whether ``data`` declares a DTD or an XML entity."""
    # Cheap pre-check: no markup opener means no DOCTYPE/ENTITY. Also cover the
    # UTF-16 forms so documents with interleaved NUL bytes are not skipped.
    if not (b"<!" in data or b"<\x00!\x00" in data or b"\x00<\x00!" in data):
        return False

    lowered = data.lower()
    if any(marker in lowered for marker in _FORBIDDEN_XML_MARKERS):
        return True

    # A UTF-16 document interleaves NUL bytes, so the ASCII markers above do
    # not match. Compare again with the NUL padding removed.
    if b"\x00" in lowered:
        compact = lowered.replace(b"\x00", b"")
        return any(marker in compact for marker in _FORBIDDEN_XML_MARKERS)
    return False


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    """Read and parse a bounded, DTD-free XML entry from an Office ZIP."""
    data = read_text_entry(zf, name, MAX_ENTRY_BYTES)

    if _contains_forbidden_xml(data):
        raise OfficeParseError(
            _("This Office document contains unsupported XML declarations.")
        )

    try:
        return ET.fromstring(data)
    except (ET.ParseError, LookupError, ValueError) as exc:
        raise OfficeParseError(
            _("This Office document contains invalid XML.")
        ) from exc
