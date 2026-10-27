# 🌌 Space Previewer (Quick Look for Ubuntu / GNOME)

A modern, fast, and resizable **Quick Look** spacebar file previewer for Linux (GNOME / Nautilus) built with **Python 3 & GTK4 / Libadwaita**.

---

## ✨ Features

- **⌨️ Instant Spacebar Preview**: Press `Space` on any file or folder in Nautilus to peek into its content.
- **🔄 Auto-Update on Navigation**: Keep the preview window open and use arrow keys `↑` `↓` `←` `→` in Nautilus to browse through files seamlessly.
- **📐 Resizable & Movable**: Freely resize, drag, and position the preview window anywhere without off-screen clipping.
- **🎨 Modern Aesthetics**: Clean Libadwaita dark/light theme integration with smooth rounded corners.
- **🖼️ Images**: PNG, JPG, WebP, GIF, SVG, BMP with scroll-wheel zoom & pan.
- **📄 Code & Text**: Syntax-highlighted preview for Python, JS, TS, HTML, CSS, JSON, YAML, Shell, SQL, Markdown, and plain text.
- **📊 CSV / TSV**: Formatted table grid view with column headers.
- **📑 PDF Documents**: Multi-page rendering with Poppler.
- **🎬 Audio & Video**: Compact media player for MP4, MKV, WebM, MP3, WAV, FLAC.
- **📦 Archives**: Lists files inside ZIP, TAR, GZ, RAR archives without extracting.
- **🔤 Fonts**: Displays font specimen text and size scales for TTF, OTF, WOFF.
- **📁 Folders**: Displays item counts, directory size, and latest modifications.

---

## 📦 Prerequisites

Install the required GTK4, Libadwaita, and Poppler dependencies for your distribution:

### Ubuntu / Debian (22.04, 24.04+)
```bash
sudo apt update
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-poppler-0.18 python3-pygments
```

### Fedora
```bash
sudo dnf install python3-gobject gtk4 libadwaita poppler-glib python3-pygments
```

### Arch Linux / Manjaro
```bash
sudo pacman -S python-gobject gtk4 libadwaita poppler-glib python-pygments
```

---

## 🚀 Installation

Run the automated installer script:

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

---

## 🗑️ Uninstallation

To cleanly remove the DBus integration:

```bash
./uninstall.sh
```

---

## ⌨️ Shortcuts

- **`Space`** or **`Escape`**: Close preview window.
- **`F`** or **`F11`**: Toggle Fullscreen.
- **`Ctrl + Scroll`** (on images): Zoom in / out.
