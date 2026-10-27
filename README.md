# Space Previewer (Quick Look for Ubuntu / GNOME)

A modern, fast, and resizable **Quick Look** spacebar file previewer for Linux (GNOME / Nautilus) built with **Python 3 & GTK4 / Libadwaita**.

---

## Features

- **Instant Spacebar Preview**: Press `Space` on any file or folder in Nautilus to peek into its content.
- **Auto-Update on Navigation**: Keep the preview window open and use the arrow keys `Up` `Down` `Left` `Right` in Nautilus to browse through files.
- **Resizable & Movable**: Freely resize, drag, and position the preview window.
- **Libadwaita Integration**: System light and dark theme, native controls and rounded corners.
- **Images**: PNG, JPG, WebP, GIF, SVG, BMP.
- **Code & Text**: Syntax-highlighted preview for Python, JS, TS, HTML, CSS, JSON, YAML, Shell, SQL, Markdown, and plain text, with in-file search.
- **CSV / TSV**: Formatted table grid view with column headers.
- **PDF Documents**: Multi-page rendering with Poppler.
- **Audio & Video**: Compact media player for MP4, MKV, WebM, MP3, WAV, FLAC.
- **Archives**: Lists files inside ZIP and TAR archives without extracting.
- **Fonts**: Displays font specimen text and size scales for TTF, OTF, WOFF.
- **Folders**: Displays item counts and a preview of the first entries.

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

Run the automated installer script:

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer copies the source to `~/.local/share/space-previewer`, registers the
`org.gnome.NautilusPreviewer` D-Bus service in your user data directory, and enables a
systemd user unit.

---

## Uninstallation

```bash
./uninstall.sh
```

This removes the D-Bus service, the user unit, and the installed files. It does not reinstall
Sushi; if you want the default GNOME previewer back, install `gnome-sushi` from your distro.

---

## Shortcuts

- **`Space`** or **`Escape`**: Close the preview window.
- **`Ctrl + F`**: Search inside text and code.
- **`F`** or **`F11`**: Toggle fullscreen.
- **Scroll** (images): Zoom in and out.
