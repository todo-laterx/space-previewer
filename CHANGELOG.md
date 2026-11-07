# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- KDE Dolphin and Cinnamon Nemo integration via a KIO context-menu service
  (`data/space-previewer.desktop` and `scripts/dolphin-service-menu.py`) and
  Nemo action (`data/space-previewer.nemo_action`) launching
  `space-previewer --standalone` for local files and folders.
- Pluggable file-manager adapter architecture (`src/app.py`, `src/integrations/__init__.py`,
  `src/integrations/nautilus.py`) separating the GTK4/Libadwaita preview core from
  Nautilus D-Bus transport (`NautilusIntegration`) and independent invocations
  (`StandaloneIntegration`).
- Multi-distro packaging & dependency checks: Fedora / RHEL `.noarch.rpm`
  (`packaging/space-previewer.spec` and `scripts/build-rpm.sh`), Arch Linux
  `packaging/PKGBUILD`, openSUSE `zypper` support in `./install.sh --check-deps`,
  and Dolphin/Nemo menu registration in `./install.sh` and `AppImage --install`.
- Unified package checksum generator (`scripts/write-checksums.sh`) across `.deb`,
  `.rpm`, and `AppImage` artifacts, and automated payload/metadata test suite
  (`tests/test_integrations.py`, `tests/test_dolphin.py`, `tests/test_packages.py`).

## [0.1.0] - 2026-11-07

### Added

- Debian (`.deb`) and `AppImage` packaging scripts (`scripts/build-deb.sh` and
  `scripts/build-appimage.sh`) alongside the user-level D-Bus installer, plus
  the official GNOME/Libadwaita application logo in `assets/` and `TRADEMARK.md`.
- Search inside the rendered Markdown preview. `Ctrl+F` no longer switches to
  Raw Code: matches are highlighted in place, the counter shows
  `current / total`, and `Enter` / `Shift+Enter` walk the results. Switching
  between Preview and Raw Code keeps the query and continues searching.
- Line-range copy in code, text and rendered Markdown previews: drag the gutter
  line numbers to select whole lines, or click a rendered Markdown block
  (Shift+click to extend), then copy the range as plain text or as a
  `path:start-end` reference. `Ctrl+Shift+C` copies the current selection as a
  reference.
- PDF preview rebuilt around a continuous, fit-width layout: pages are
  rasterised lazily around the viewport with a bounded texture cache, the window
  opens at a screen-appropriate size, and previous/next page navigation scrolls
  with a short ease-out animation. `PageUp`/`PageDown` and `Home`/`End` work
  while the preview has focus.
- An explicit selection colour on the code surface so dragged text is visible.
- GTK4/Libadwaita preview window driven over D-Bus for Nautilus.
- Full preview D-Bus contract: `SelectionEvent`, `NavigateTo`, `Rename`, `Trash`, a live
  `ParentHandle`, and startup activation tokens.
- Syntax-highlighted preview for text and code files, with in-file search in an overlay.
- Markdown preview, including locally rendered Mermaid diagrams.
- HTML preview through WebKitGTK 6.0, optional at runtime, with remote content blocked by
  default and a source-view fallback when WebKit is missing.
- Image preview for common image formats, including animated GIF and SVG, with
  `Ctrl+Scroll` zoom.
- Multi-page PDF preview with Poppler, capped at 100 rendered pages.
- Audio and video playback with GStreamer, including play/pause from the keyboard.
- CSV and TSV table preview, bounded to 5000 rows and 100 columns.
- ZIP and TAR archive listing without extracting files, including sizes and an
  encrypted-entry rejection path.
- Font specimen preview for TTF, OTF, WOFF and WOFF2 files.
- Folder preview with item counts, a sample of the first entries, and a background
  size scan with a two-second budget.
- Text extraction for DOCX, XLSX and PPTX documents, reading the ZIP/XML parts directly
  with per-entry and total size caps.
- Bounded parsing for every format: 5 MB text, 2 MB Markdown, 20 MB per Office entry,
  5000 archive entries, 100 PDF pages, 50 megapixels per image. Truncation is shown in
  the status bar or as an inline note.
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

- HTML remote content is blocked with a content security policy, not just navigation policy,
  and local pages cannot read other `file://` documents.
- Office XML parts reject `DOCTYPE` and `ENTITY` declarations, and archives reject
  encrypted entries before any decompression.
- No telemetry and no network access without an explicit opt-in.
