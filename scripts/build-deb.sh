#!/usr/bin/env bash
# Build the Debian/Ubuntu (.deb) package for Space Previewer.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

VERSION="$(tr -d '[:space:]' < "$DIR/VERSION")"
ARCH="amd64"
PKG_DIR="$DIR/build/deb"
DEB_NAME="space-previewer_${VERSION}_${ARCH}.deb"

echo "==> Building ${DEB_NAME}..."

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN" \
         "$PKG_DIR/usr/bin" \
         "$PKG_DIR/usr/share/space-previewer" \
         "$PKG_DIR/usr/share/dbus-1/services" \
         "$PKG_DIR/usr/share/icons/hicolor/512x512/apps" \
         "$PKG_DIR/usr/share/doc/space-previewer"

# 1. Copy application sources (without bytecode caches)
cp -R "$DIR/src/." "$PKG_DIR/usr/share/space-previewer/"
find "$PKG_DIR/usr/share/space-previewer" -type d -name __pycache__ -prune \
    -exec rm -rf {} + 2>/dev/null || true
find "$PKG_DIR/usr/share/space-previewer" -name '*.pyc' -delete 2>/dev/null || true
chmod 0755 "$PKG_DIR/usr/share/space-previewer/main.py"

mkdir -p "$PKG_DIR/usr/share/space-previewer/po"
cp -R "$DIR/po/." "$PKG_DIR/usr/share/space-previewer/po/"

# 2. Compile gettext catalogs (.po -> .mo)
compile_po() {
    local po_file="$1" mo_file="$2"
    if command -v msgfmt >/dev/null 2>&1; then
        msgfmt --check --output-file="$mo_file" "$po_file"
        return 0
    fi
    if /usr/bin/python3 -c "import babel" >/dev/null 2>&1; then
        /usr/bin/python3 - "$po_file" "$mo_file" <<'PY'
import sys
from babel.messages import pofile
from babel.messages.mofile import write_mo

with open(sys.argv[1], "rb") as handle:
    catalog = pofile.read_po(handle)
with open(sys.argv[2], "wb") as handle:
    write_mo(handle, catalog)
PY
        return 0
    fi
    return 1
}

for po_file in "$DIR"/po/*.po; do
    [ -e "$po_file" ] || continue
    lang="$(basename "$po_file" .po)"
    mo_dir="$PKG_DIR/usr/share/space-previewer/locale/$lang/LC_MESSAGES"
    mkdir -p "$mo_dir"
    compile_po "$po_file" "$mo_dir/space-previewer.mo"
done

# 3. Install CLI launcher
cat > "$PKG_DIR/usr/bin/space-previewer" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/share/space-previewer/main.py "$@"
EOF
chmod 0755 "$PKG_DIR/usr/bin/space-previewer"

# Dolphin discovers system service menus directly; no per-user hooks are needed.
install -Dm644 "$DIR/data/space-previewer.desktop" \
    "$PKG_DIR/usr/share/kio/servicemenus/space-previewer.desktop"

# 4. Install D-Bus activation service
cat > "$PKG_DIR/usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service" <<'EOF'
[D-BUS Service]
Name=org.gnome.NautilusPreviewer
Exec=/usr/bin/python3 /usr/share/space-previewer/main.py
EOF
chmod 0644 "$PKG_DIR/usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service"

# 5. Install icon and documentation
cp "$DIR/assets/logo-512.png" "$PKG_DIR/usr/share/icons/hicolor/512x512/apps/space-previewer.png"
chmod 0644 "$PKG_DIR/usr/share/icons/hicolor/512x512/apps/space-previewer.png"

cp "$DIR/LICENSE" "$DIR/TRADEMARK.md" "$DIR/README.md" "$PKG_DIR/usr/share/doc/space-previewer/"
cp "$DIR/docs/DOLPHIN.md" "$PKG_DIR/usr/share/doc/space-previewer/"
cp "$DIR/docs/INTEGRATIONS.md" "$PKG_DIR/usr/share/doc/space-previewer/"
chmod 0644 "$PKG_DIR/usr/share/doc/space-previewer/"*

# 6. Create DEBIAN/control
cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: space-previewer
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Space Previewer Contributors <https://github.com/todo-laterx/space-previewer>
Depends: python3, python3-gi, python3-gi-cairo, python3-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gdkpixbuf-2.0, gir1.2-pango-1.0, gir1.2-poppler-0.18, python3-pygments, python3-markdown-it
Recommends: gir1.2-webkit-6.0, libwebkitgtk-6.0-4
Description: Quick Look file previewer for Nautilus and Dolphin
 Space Previewer is a fast, resizable GTK4 and Libadwaita file previewer
 driven over D-Bus by GNOME Files (Nautilus). It previews Markdown with
 in-preview search and Mermaid diagrams, syntax-highlighted code with
 line-range reference copying, continuous fit-width PDFs, Office documents,
 CSV/TSV tables, archives, images, fonts, audio, video, and folders.
 A Dolphin context-menu action opens local files in standalone mode.
EOF

# 7. Divert gnome-sushi's D-Bus service cleanly in preinst / postrm
cat > "$PKG_DIR/DEBIAN/preinst" <<'EOF'
#!/bin/sh
set -e
SERVICE="/usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service"
if [ "$1" = "install" ] || [ "$1" = "upgrade" ]; then
    dpkg-divert --package space-previewer --add --rename \
        --divert "${SERVICE}.sushi" "$SERVICE" >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/preinst"

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v pkill >/dev/null 2>&1; then
    pkill -x sushi >/dev/null 2>&1 || true
    pkill -f "/usr/share/space-previewer/main.py" >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postinst"

cat > "$PKG_DIR/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
SERVICE="/usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service"
if [ "$1" = "remove" ] || [ "$1" = "abort-install" ] || [ "$1" = "disappear" ]; then
    dpkg-divert --package space-previewer --remove --rename \
        --divert "${SERVICE}.sushi" "$SERVICE" >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postrm"

mkdir -p "$DIR/dist"
dpkg-deb --build --root-owner-group "$PKG_DIR" "$DIR/dist/$DEB_NAME"

(cd "$DIR/dist" && sha256sum *.deb *.AppImage 2>/dev/null > SHA256SUMS || true)
echo "==> Built: dist/$DEB_NAME"
