# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-27

### Added

- GTK4/Libadwaita preview window driven over D-Bus for Nautilus.
- Full preview D-Bus contract: `SelectionEvent`, `NavigateTo`, `Rename`, `Trash`, a live
  `ParentHandle`, and startup activation tokens.
- Syntax-highlighted preview for text and code files, with in-file search in an overlay.
- Markdown preview, including locally rendered Mermaid diagrams.
- HTML preview through WebKitGTK 6.0, optional at runtime, with remote content blocked by
  default and a source-view fallback when WebKit is missing.
- Image preview for common image formats.
- Multi-page PDF preview with Poppler.
- Audio and video playback with GStreamer.
- CSV and TSV table preview.
- ZIP and TAR archive listing without extracting files.
- Font specimen preview for TTF, OTF, WOFF and WOFF2 files.
- Folder preview with item counts and a sample of the first entries.
- Text extraction for DOCX, XLSX and PPTX documents.
- Viewer plugin registry with a versioned API and a `SPACE_PREVIEWER_PLUGINS=0` kill switch.
- English and Vietnamese message catalogs, locale-aware sizes and dates, and
  `SPACE_PREVIEWER_LANG` for testing.
- Header controls and a one-line status bar shared by all viewers.

### Changed

- D-Bus activation replaces the systemd user unit; the process exits after the preview closes.
- Neutral Libadwaita styling with one accent, replacing the Catppuccin palette.
- Per-viewer toolbars were folded into the window header; search is a non-grabbing overlay.
- Mermaid uses the remote renderer only when `SPACE_PREVIEWER_ALLOW_NETWORK=1`.

### Security

- HTML remote content is blocked with a content security policy, not just navigation policy.
- No telemetry and no network access without an explicit opt-in.
