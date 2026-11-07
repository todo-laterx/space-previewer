<div align="center">

<img src="assets/logo.webp" alt="Space Previewer Logo" width="128" height="128" />

# Space Previewer

**Quick Look file previewer for Linux desktops — native GNOME / Nautilus spacebar integration, KDE Dolphin service menu, and standalone CLI, built with GTK4 + Libadwaita.**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-GNOME%20%7C%20KDE%20%7C%20Wayland%20%26%20X11-lightgrey.svg)](#tested-environments)
[![UI](https://img.shields.io/badge/UI-GTK4%20%2B%20Libadwaita-3867D6.svg)](#features)
[![Version](https://img.shields.io/badge/Version-0.2.0-2ea44f.svg)](VERSION)

</div>

---

## Why Space Previewer vs `gnome-sushi`

| Capability | Default `gnome-sushi` | Space Previewer |
|---|---|---|
| **Markdown (`.md`, `.mdx`)** | Raw plain-text source only | Rendered GFM preview (tables, task lists, callouts), offline Cairo Mermaid diagrams, Raw/Preview toggle |
| **In-file search (`Ctrl+F`)** | Not supported | Non-grabbing overlay search in code, plain text, and rendered Markdown (`Enter` / `Shift+Enter`) |
| **Line & block quote copy** | Not supported | Drag line numbers in code/text or click rendered Markdown blocks (`Shift+Click` for range) to copy text or `path:start-end` reference |
| **CSV / TSV** | Plain text | Formatted scrollable table grid with column headers |
| **Archives (`.zip`, `.tar.*`)** | Summary size only | Full file tree listing with entry sizes without extracting to disk |
| **Office (`.docx`, `.xlsx`, `.pptx`)** | Requires full LibreOffice stack | Zero-dependency direct ZIP/XML text & sheet extraction with strict input bounds |
| **Folders** | Item count only | Item counts, preview of the first entries, and non-blocking background total size scan |
| **PDF Documents** | Single-page view | Continuous fit-width viewport with lazy page rasterisation and smooth `PageUp`/`PageDown` navigation |

---

## Features

- **Instant Spacebar Preview**: Press `Space` on any file or folder in Nautilus to peek into its content.
- **Auto-Update on Navigation**: Keep the preview window open and use the arrow keys `Up` `Down` `Left` `Right` in Nautilus to browse through files.
- **Stacked with Files**: Attaches as a transient child of the active Nautilus window on both Wayland and X11, stacking cleanly under the Files icon in the GNOME Dock.
- **Copy a line range**: Text and code are selectable; drag the line numbers to pick whole lines, or click a rendered Markdown block (`Shift+Click` to extend). Copy the range as plain text, or copy a `path:start-end` reference (`Ctrl+Shift+C`).
- **One chrome for every viewer**: A single `Adw.HeaderBar` and one bottom status bar. File type, size and metadata live in the status bar; viewers never add their own toolbar row.
- **Images**: PNG, JPG, WebP, GIF (animated), SVG, BMP; `Ctrl+Scroll` zooms.
- **Code & Text**: Syntax-highlighted preview for Python, JS, TS, HTML, CSS, JSON, YAML, Shell, SQL, Markdown, and plain text, with in-file search and JSON pretty-printing.
- **Markdown**: Rendered preview with GFM tables, task lists, callouts, Mermaid diagrams (local Cairo renderer; remote `mermaid.ink` opt-in) and a raw source toggle.
- **HTML**: Local pages rendered with WebKitGTK 6.0 when installed; remote content is blocked by default via CSP and the page falls back to source view without WebKit.
- **CSV / TSV**: Formatted table grid view with column headers.
- **PDF Documents**: Continuous, fit-width rendering with Poppler. Pages render lazily as they scroll into view, with previous/next page buttons, `PageUp`/`PageDown`, and a smooth scroll animation for page jumps.
- **Office**: DOCX, XLSX and PPTX read directly from their ZIP/XML parts; legacy `.doc`, `.xls` and `.ppt` fall back to a summary and the default app.
- **Audio & Video**: Compact GStreamer media player for MP4, MKV, WebM, MP3, WAV, FLAC.
- **Archives**: Lists files inside ZIP and TAR archives without extracting.
- **Fonts**: Displays font specimen text and size scales for TTF, OTF, WOFF, WOFF2.
- **Folders**: Item counts and a preview of the first entries; total size is computed in the background.
- **Translations**: Full English and Vietnamese catalogs; `SPACE_PREVIEWER_LANG=vi` forces a language.
- **Plugins**: External viewers discovered from `~/.local/share/space-previewer/plugins/1` and `/usr/share/space-previewer/plugins/1`; see [docs/PLUGINS.md](docs/PLUGINS.md).

---

## Tested Environments

| Distribution | Session / File Manager | Packaging | Notes |
|---|---|---|---|
| **Ubuntu 22.04 / 24.04 / 26.04+ / Linux Mint** | GNOME (Nautilus), KDE Plasma (Dolphin) & Cinnamon (Nemo) | `.deb` / `AppImage` / `./install.sh` | Full Nautilus D-Bus contract (`NautilusPreviewer2`), `dpkg-divert` coexistence with `gnome-sushi`, plus Dolphin & Nemo context menus |
| **Debian 12 / 13** | GNOME (Nautilus), KDE Plasma (Dolphin) & Cinnamon (Nemo) | `.deb` / `AppImage` / `./install.sh` | Clean `dpkg-divert` coexistence with `gnome-sushi`, plus Dolphin & Nemo context menus |
| **Fedora 40+** | GNOME (Nautilus), KDE Spin (Dolphin) & Cinnamon (Nemo) | `.rpm` / `AppImage` / `./install.sh` | Native `.noarch.rpm` with Nautilus D-Bus service, Dolphin service menu, and Nemo action |
| **Arch Linux / Manjaro / EndeavourOS** | GNOME (Nautilus), KDE Plasma (Dolphin) & Cinnamon (Nemo) | `PKGBUILD` / `AppImage` / `./install.sh` | Native Arch package via `packaging/PKGBUILD` (`makepkg -si`) or user install |
| **openSUSE Tumbleweed / Leap** | GNOME (Nautilus), KDE Plasma (Dolphin) & Cinnamon (Nemo) | `AppImage` / `./install.sh` | Native GTK4 + Libadwaita runtime packages via `zypper` (`./install.sh --check-deps`) |

---

## Prerequisites

Install the required GTK4, Libadwaita, and Poppler system packages for your distribution (handled automatically when installing the `.deb` package on Ubuntu/Debian or the `.rpm` package on Fedora).

### Ubuntu / Debian / Linux Mint (22.04, 24.04+)
```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0 \
  gir1.2-poppler-0.18 python3-pygments python3-markdown-it
```

Optional HTML preview: `sudo apt install gir1.2-webkit-6.0 libwebkitgtk-6.0-4`

### Fedora / RHEL 9+
```bash
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita poppler-glib \
  python3-pygments python3-markdown-it
```

Optional HTML preview: `sudo dnf install webkitgtk6.0`

### Arch Linux / Manjaro / EndeavourOS
```bash
sudo pacman -S python-gobject python-cairo gtk4 libadwaita poppler-glib \
  python-pygments python-markdown-it
```

Optional HTML preview: `sudo pacman -S webkitgtk-6.0`

### openSUSE Tumbleweed / Leap
```bash
sudo zypper install python3-gobject python3-gobject-Gdk python3-gobject-cairo \
  python3-cairo python3-Pygments python3-markdown-it-py \
  typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 typelib-1_0-GdkPixbuf-2_0 \
  typelib-1_0-Pango-1_0 typelib-1_0-Poppler-0_18
```

Optional HTML preview: `sudo zypper install typelib-1_0-WebKit-6_0`

---

## Installation

### Option 1: Debian / Ubuntu / Kubuntu package (`.deb`)

```bash
sudo apt install ./dist/space-previewer_0.1.0_amd64.deb
```

The `.deb` package installs both the Nautilus D-Bus preview service and the KDE Dolphin context-menu action (`/usr/share/kio/servicemenus/space-previewer.desktop`). It uses `dpkg-divert` on `org.gnome.NautilusPreviewer.service`, so it installs cleanly alongside `gnome-sushi` and restores `gnome-sushi` automatically on removal (`sudo apt remove space-previewer`).

### Option 2: Fedora / RHEL package (`.rpm`)

```bash
sudo dnf install ./dist/space-previewer-0.1.0-1.noarch.rpm
```

The `.rpm` package installs both the Nautilus D-Bus preview service and the KDE Dolphin context-menu action. Because RPM does not provide `dpkg-divert` and both packages own `/usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service`, the RPM declares `Conflicts: sushi`. On Fedora Workstation where `sushi` is preinstalled, pass `--allowerasing`:

```bash
sudo dnf install --allowerasing ./dist/space-previewer-0.1.0-1.noarch.rpm
```

### Option 3: Arch Linux / Manjaro (`PKGBUILD`)

```bash
cd packaging
makepkg -si
```

The `packaging/PKGBUILD` installs the Nautilus D-Bus service, KDE Dolphin service menu, Cinnamon Nemo action, gettext catalogs, and `/usr/bin/space-previewer`.

### Option 4: Portable `AppImage` (`x86_64`)

```bash
chmod +x ./dist/Space-Previewer-0.1.0-x86_64.AppImage
./dist/Space-Previewer-0.1.0-x86_64.AppImage --install
```

`--install` registers the Nautilus D-Bus service, the KDE Dolphin service menu, the Cinnamon Nemo action, and the `~/.local/bin/space-previewer` symlink for the current user. To unregister:

```bash
./dist/Space-Previewer-0.1.0-x86_64.AppImage --uninstall
```

### Option 5: User-level source install (no root required)

Check dependencies first:

```bash
./install.sh --check-deps
```

Then install for the current user (Nautilus D-Bus service + `~/.local/bin/space-previewer` CLI):

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer copies the source to `~/.local/share/space-previewer`, installs the
`org.gnome.NautilusPreviewer` D-Bus activation file in `~/.local/share/dbus-1/services`,
compiles translations (with `msgfmt`, or with Python Babel when gettext is not installed),
and reloads Nautilus. To uninstall:

```bash
./uninstall.sh
```

### Dolphin / KDE Plasma Service Menu (from source checkout)

If you use KDE Dolphin without installing the `.deb` or `.rpm` package, you can install a per-user Dolphin service menu that opens any local file or folder in standalone mode (`--standalone`), without touching the Nautilus/Sushi D-Bus service:

```bash
python3 scripts/dolphin-service-menu.py
```

To remove the per-user Dolphin menu:

```bash
python3 scripts/dolphin-service-menu.py --uninstall
```

See [docs/DOLPHIN.md](docs/DOLPHIN.md) for full details on Dolphin integration and migration between source and package installs.

---

## Building Packages from Source

For the shared preview core and file-manager adapter architecture, see
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).

Build the `.deb`, Fedora `.rpm`, and `AppImage` artifacts into `dist/` (with unified checksums in `dist/SHA256SUMS`):

```bash
bash scripts/build-deb.sh
bash scripts/build-rpm.sh
bash scripts/build-appimage.sh
```

Run the package payload and metadata test suite (requires `dpkg-deb`, `rpmbuild`, `rpm`, `rpm2cpio`, `cpio`, and `msgfmt`):

```bash
python3 -m unittest discover -s tests -p 'test_packages.py' -v
```

---

## Shortcuts

- **`Space`** or **`Escape`**: Close the preview window (or the search card / line selection first when active).
- **`Ctrl + F`**: Open the non-grabbing search card. In Markdown it searches the rendered preview; switching to Raw Code keeps the query.
- **`Ctrl + Shift + C`**: Copy the selected lines, or the text selection, as a `path:start-end` reference.
- **Drag line numbers** (text and code): Select whole lines and show the copy card.
- **Click / Shift + Click** (Markdown preview): Select one rendered block, or a range of blocks, for copying.
- **`Enter` / `Shift + Enter`**: Next or previous search match.
- **`Ctrl + ?`**: Show the keyboard shortcut sheet.
- **`F`** or **`F11`**: Toggle fullscreen.
- **`O`**: Open the file with the default application.
- **`P`**: Play or pause audio and video.
- **`PageUp` / `PageDown`** (PDF): Previous or next page, animated.
- **`Home` / `End`** (PDF): First or last page.
- **`Ctrl + Scroll`** (images): Zoom in and out.
- **`Up` / `Down` / `Left` / `Right`** *(Nautilus integration)*: Move the selection in Files; the preview follows.
- **`F2`** *(Nautilus integration)*: Close the preview and start renaming in Files.
- **`Delete`** *(Nautilus integration)*: Move the file to the trash from Files.

---

## Preview Limits & Security

Parsers are bounded so a hostile file cannot exhaust memory or block the UI. The full
table lives in [SECURITY.md](SECURITY.md): 5 MB of text, 2 MB of Markdown, 20 MB per
Office entry, 5000 archive entries, 100 PDF pages, 50 megapixels per image, and a
20,000-entry folder scan with a two-second budget. Remote HTML and Mermaid rendering
are off until you opt in with `SPACE_PREVIEWER_ALLOW_NETWORK=1`.

---

## License & Trademark

- Code is licensed under the [GNU General Public License v3.0](LICENSE).
- Brand and logo usage is governed by [TRADEMARK.md](TRADEMARK.md).
