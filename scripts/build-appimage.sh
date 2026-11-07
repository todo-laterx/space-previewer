#!/usr/bin/env bash
# Build the portable AppImage for Space Previewer.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

VERSION="$(tr -d '[:space:]' < "$DIR/VERSION")"
APPDIR="$DIR/build/AppDir"
CACHE="$DIR/build/cache"
DIST="$DIR/dist"
APPIMAGE_NAME="Space-Previewer-${VERSION}-x86_64.AppImage"
APPIMAGE_OUT="$DIST/$APPIMAGE_NAME"

echo "==> Building ${APPIMAGE_NAME}..."

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/space-previewer/data" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
         "$CACHE" \
         "$DIST"

# 1. Copy application sources (without bytecode caches)
cp -R "$DIR/src/." "$APPDIR/usr/share/space-previewer/"
cp "$DIR/data/space-previewer.desktop" "$APPDIR/usr/share/space-previewer/data/"
cp "$DIR/data/space-previewer.nemo_action" "$APPDIR/usr/share/space-previewer/data/"
find "$APPDIR/usr/share/space-previewer" -type d -name __pycache__ -prune \
    -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/usr/share/space-previewer" -name '*.pyc' -delete 2>/dev/null || true
chmod 0755 "$APPDIR/usr/share/space-previewer/main.py"

mkdir -p "$APPDIR/usr/share/space-previewer/po"
cp -R "$DIR/po/." "$APPDIR/usr/share/space-previewer/po/"
mkdir -p "$APPDIR/usr/share/space-previewer/assets"
cp -R "$DIR/assets/." "$APPDIR/usr/share/space-previewer/assets/"

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
    mo_dir="$APPDIR/usr/share/space-previewer/locale/$lang/LC_MESSAGES"
    mkdir -p "$mo_dir"
    compile_po "$po_file" "$mo_dir/space-previewer.mo"
done

# 3. Copy icons and desktop metadata (NoDisplay=true keeps the preview stacked with Nautilus)
cp "$DIR/assets/logo-512.png" "$APPDIR/space-previewer.png"
cp "$DIR/assets/logo-512.png" "$APPDIR/.DirIcon"
cp "$DIR/assets/logo-512.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/space-previewer.png"

cat > "$APPDIR/space-previewer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Space Previewer
Comment=Quick Look spacebar file previewer for GNOME / Nautilus
Exec=space-previewer %U
Icon=space-previewer
Terminal=false
NoDisplay=true
Categories=Utility;FileTools;GTK;GNOME;
EOF

# 4. Create AppRun with built-in --install / --uninstall D-Bus activation support
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
set -eu

HERE="$(dirname "$(readlink -f "$0")")"
APP_PATH="${APPIMAGE:-$HERE/AppRun}"

case "${1:-}" in
    --install)
        DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
        case "$DATA_DIR" in
            /*) ;;
            *) DATA_DIR="$HOME/.local/share" ;;
        esac
        DBUS_DIR="$DATA_DIR/dbus-1/services"
        DOLPHIN_DIR="$DATA_DIR/kio/servicemenus"
        NEMO_DIR="$DATA_DIR/nemo/actions"
        BIN_DIR="$HOME/.local/bin"
        ICON_DIR="$DATA_DIR/icons/hicolor/512x512/apps"
        mkdir -p "$DBUS_DIR" "$DOLPHIN_DIR" "$NEMO_DIR" "$BIN_DIR" "$ICON_DIR"
        cat > "$DBUS_DIR/org.gnome.NautilusPreviewer.service" <<SVC
[D-BUS Service]
Name=org.gnome.NautilusPreviewer
Exec=$APP_PATH
SVC
        sed "s|Exec=/usr/bin/space-previewer |Exec=\"$APP_PATH\" |" \
            "$HERE/usr/share/space-previewer/data/space-previewer.desktop" \
            > "$DOLPHIN_DIR/space-previewer.desktop"
        chmod 0755 "$DOLPHIN_DIR/space-previewer.desktop"
        sed "s|Exec=/usr/bin/space-previewer |Exec=\"$APP_PATH\" |" \
            "$HERE/usr/share/space-previewer/data/space-previewer.nemo_action" \
            > "$NEMO_DIR/space-previewer.nemo_action"
        chmod 0644 "$NEMO_DIR/space-previewer.nemo_action"
        ln -sfn "$APP_PATH" "$BIN_DIR/space-previewer"
        cp -f "$HERE/space-previewer.png" "$ICON_DIR/space-previewer.png"
        if command -v pkill >/dev/null 2>&1; then
            pkill -x sushi >/dev/null 2>&1 || true
        fi
        if command -v nautilus >/dev/null 2>&1; then
            nautilus -q >/dev/null 2>&1 || true
        fi
        echo "Space Previewer AppImage registered for Nautilus, Dolphin, and Nemo."
        exit 0
        ;;
    --uninstall)
        DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
        case "$DATA_DIR" in
            /*) ;;
            *) DATA_DIR="$HOME/.local/share" ;;
        esac
        rm -f "$DATA_DIR/dbus-1/services/org.gnome.NautilusPreviewer.service"
        rm -f "$DATA_DIR/kio/servicemenus/space-previewer.desktop"
        rm -f "$DATA_DIR/nemo/actions/space-previewer.nemo_action"
        rm -f "$HOME/.local/bin/space-previewer"
        if command -v nautilus >/dev/null 2>&1; then
            nautilus -q >/dev/null 2>&1 || true
        fi
        echo "Space Previewer AppImage unregistered."
        exit 0
        ;;
esac

exec /usr/bin/python3 "$HERE/usr/share/space-previewer/main.py" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"
ln -sfn ../../AppRun "$APPDIR/usr/bin/space-previewer"

# 5. Locate or download appimagetool
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [ -z "$APPIMAGETOOL" ] && [ -x "$CACHE/appimagetool-x86_64.AppImage" ]; then
    APPIMAGETOOL="$CACHE/appimagetool-x86_64.AppImage"
fi
if [ -z "$APPIMAGETOOL" ] && [ -x "/media/tuannt/Data/DEV/Zalux/build/cache/appimagetool-x86_64.AppImage" ]; then
    APPIMAGETOOL="/media/tuannt/Data/DEV/Zalux/build/cache/appimagetool-x86_64.AppImage"
fi
if [ -z "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool-x86_64.AppImage..."
    curl -fsSL --max-time 180 -o "$CACHE/appimagetool-x86_64.AppImage" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod 0755 "$CACHE/appimagetool-x86_64.AppImage"
    APPIMAGETOOL="$CACHE/appimagetool-x86_64.AppImage"
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$APPIMAGE_OUT" >/dev/null
chmod 0755 "$APPIMAGE_OUT"

bash "$DIR/scripts/write-checksums.sh" "$DIST"
echo "==> Built: dist/$APPIMAGE_NAME"
