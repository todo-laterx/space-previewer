<p align="center">
  <img src="assets/logo.webp" alt="Space Previewer Logo" width="144" height="144" />
</p>

# Space Previewer (Quick Look for Ubuntu / GNOME)

A modern, fast, and resizable **Quick Look** spacebar file previewer for Linux (GNOME / Nautilus) built with **Python 3 & GTK4 / Libadwaita**.

---

## Features

- **Instant Spacebar Preview**: Press `Space` on any file or folder in Nautilus to peek into its content.
- **Auto-Update on Navigation**: Keep the preview window open and use the arrow keys `Up` `Down` `Left` `Right` in Nautilus to browse through files.
- **Resizable & Movable**: Freely resize, drag, and position the preview window.
- **Libadwaita Integration**: System light and dark theme, native controls and rounded corners.
- **One chrome for every viewer**: A single header bar and one status bar. File type, size and metadata live in the status bar; viewers never add their own toolbar row.
- **Images**: PNG, JPG, WebP, GIF (animated), SVG, BMP; `Ctrl+Scroll` zooms.
- **Code & Text**: Syntax-highlighted preview for Python, JS, TS, HTML, CSS, JSON, YAML, Shell, SQL, Markdown, and plain text, with in-file search.
- **Markdown**: Rendered preview with GFM tables, task lists, callouts, Mermaid diagrams (opt-in) and a raw source toggle.
- **HTML**: Local pages rendered with WebKitGTK when installed; remote content is blocked by default and the page falls back to source view without WebKit.
- **CSV / TSV**: Formatted table grid view with column headers.
- **PDF Documents**: Multi-page rendering with Poppler.
- **Office**: DOCX, XLSX and PPTX read directly from their ZIP/XML parts; legacy `.doc`, `.xls` and `.ppt` fall back to a summary and the default app.
- **Audio & Video**: Compact media player for MP4, MKV, WebM, MP3, WAV, FLAC.
- **Archives**: Lists files inside ZIP and TAR archives without extracting.
- **Fonts**: Displays font specimen text and size scales for TTF, OTF, WOFF.
- **Folders**: Item counts and a preview of the first entries; total size is computed in the background.
- **Translations**: Full English and Vietnamese catalogs; `SPACE_PREVIEWER_LANG=vi` forces a language.
- **Plugins**: Sushi-style external viewers discovered from `~/.local/share/space-previewer/plugins/1` and `/usr/share/space-previewer/plugins/1`; see [docs/PLUGINS.md](docs/PLUGINS.md).

---

## Prerequisites

Install the required GTK4, Libadwaita, and Poppler dependencies for your distribution.

### Ubuntu / Debian (22.04, 24.04+)
```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0 \
  gir1.2-poppler-0.18 python3-pygments python3-markdown-it
```

Optional HTML preview: `sudo apt install gir1.2-webkit-6.0 libwebkitgtk-6.0-4`

### Fedora
```bash
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita poppler-glib \
  python3-pygments python3-markdown-it
```

Optional HTML preview: `sudo dnf install webkitgtk6.0`

### Arch Linux / Manjaro
```bash
sudo pacman -S python-gobject python-cairo gtk4 libadwaita poppler-glib \
  python-pygments python-markdown-it
```

Optional HTML preview: `sudo pacman -S webkitgtk-6.0`

---

## Installation

Check dependencies first:

```bash
./install.sh --check-deps
```

Then install for the current user:

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer copies the source to `~/.local/share/space-previewer`, installs the
`org.gnome.NautilusPreviewer` D-Bus activation file in `~/.local/share/dbus-1/services`,
compiles translations (with `msgfmt`, or with Python Babel when gettext is not installed),
and reloads Nautilus. It does not need root and it does not create a systemd unit.

---

## Uninstallation

```bash
./uninstall.sh
```

This removes the D-Bus service, the user unit, and the installed files. It does not reinstall
Sushi; if you want the default GNOME previewer back, install `gnome-sushi` from your distro.

---

## Shortcuts

- **`Space`** or **`Escape`**: Close the preview window (or the search card first when it is open).
- **`Ctrl + F`**: Open the non-grabbing search card for text, code and Markdown source.
- **`Enter` / `Shift + Enter`**: Next or previous search match.
- **`Ctrl + ?`**: Show the shortcut sheet.
- **`F`** or **`F11`**: Toggle fullscreen.
- **`O`**: Open the file with the default application.
- **`P`**: Play or pause audio and video.
- **`F2`**: Close the preview and start renaming in Files.
- **`Delete`**: Move the file to the trash from Files.
- **`Up` / `Down`**: Move the selection in Files; the preview follows.
- **`Ctrl + Scroll`** (images): Zoom in and out.

## Preview limits

Parsers are bounded so a hostile file cannot exhaust memory or block the UI. The full
table lives in [SECURITY.md](SECURITY.md): 5 MB of text, 2 MB of Markdown, 20 MB per
Office entry, 5000 archive entries, 100 PDF pages, 50 megapixels per image, and a
20,000-entry folder scan with a two-second budget. Remote HTML and Mermaid rendering
are off until you opt in with `SPACE_PREVIEWER_ALLOW_NETWORK=1`.

