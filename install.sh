#!/bin/bash
# Install Space Previewer for the current user.
#
# The previewer is D-Bus activated: Nautilus starts it on demand through the
# service file in ~/.local/share/dbus-1/services. There is no systemd unit and
# no root access is required.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"
BIN_DIR="$HOME/.local/bin"
APP_INSTALL_DIR="$HOME/.local/share/space-previewer"
LEGACY_UNIT="$HOME/.config/systemd/user/space-previewer.service"

DBUS_NAME="org.gnome.NautilusPreviewer"
DBUS_PATH="/org/gnome/NautilusPreviewer"
SERVICE_FILE="$DBUS_SERVICES_DIR/$DBUS_NAME.service"

# ---------------------------------------------------------------------------
# Dependency check (--check-deps)
# ---------------------------------------------------------------------------

MISSING_REQUIRED=0
MISSING_OPTIONAL=0
REQUIRED_PKGS=()
OPTIONAL_PKGS=()
PM=""

detect_pm() {
    if command -v apt-get >/dev/null 2>&1; then
        PM="apt"
    elif command -v dnf >/dev/null 2>&1; then
        PM="dnf"
    elif command -v pacman >/dev/null 2>&1; then
        PM="pacman"
    elif command -v zypper >/dev/null 2>&1; then
        PM="zypper"
    fi
}

install_cmd() {
    case "$1" in
        apt) echo "sudo apt install" ;;
        dnf) echo "sudo dnf install" ;;
        pacman) echo "sudo pacman -S" ;;
        zypper) echo "sudo zypper install" ;;
    esac
}

# Map a dependency key to distro package name(s).
pkg_for() {
    local key="$1" pm="$2"
    case "$key:$pm" in
        python3:apt|python3:dnf|python3:zypper) echo "python3" ;;
        python3:pacman) echo "python" ;;
        gi:apt) echo "python3-gi" ;;
        gi:dnf) echo "python3-gobject" ;;
        gi:pacman) echo "python-gobject" ;;
        gi:zypper) echo "python3-gobject python3-gobject-Gdk" ;;
        pygments:apt|pygments:dnf) echo "python3-pygments" ;;
        pygments:pacman) echo "python-pygments" ;;
        pygments:zypper) echo "python3-Pygments" ;;
        markdown_it:apt|markdown_it:dnf) echo "python3-markdown-it" ;;
        markdown_it:pacman) echo "python-markdown-it" ;;
        markdown_it:zypper) echo "python3-markdown-it-py" ;;
        cairo:apt) echo "python3-cairo python3-gi-cairo" ;;
        cairo:dnf) echo "python3-cairo" ;;
        cairo:pacman) echo "python-cairo" ;;
        cairo:zypper) echo "python3-cairo python3-gobject-cairo" ;;
        gtk:apt) echo "gir1.2-gtk-4.0" ;;
        gtk:dnf) echo "gtk4" ;;
        gtk:pacman) echo "gtk4" ;;
        gtk:zypper) echo "typelib-1_0-Gtk-4_0" ;;
        adw:apt) echo "gir1.2-adw-1" ;;
        adw:dnf) echo "libadwaita" ;;
        adw:pacman) echo "libadwaita" ;;
        adw:zypper) echo "typelib-1_0-Adw-1" ;;
        gdkpixbuf:apt) echo "gir1.2-gdkpixbuf-2.0" ;;
        gdkpixbuf:dnf) echo "gdk-pixbuf2" ;;
        gdkpixbuf:pacman) echo "gdk-pixbuf2" ;;
        gdkpixbuf:zypper) echo "typelib-1_0-GdkPixbuf-2_0" ;;
        pango:apt) echo "gir1.2-pango-1.0" ;;
        pango:dnf) echo "pango" ;;
        pango:pacman) echo "pango" ;;
        pango:zypper) echo "typelib-1_0-Pango-1_0" ;;
        poppler:apt) echo "gir1.2-poppler-0.18" ;;
        poppler:dnf) echo "poppler-glib" ;;
        poppler:pacman) echo "poppler-glib" ;;
        poppler:zypper) echo "typelib-1_0-Poppler-0_18" ;;
        webkit:apt) echo "gir1.2-webkit-6.0 libwebkitgtk-6.0-4" ;;
        webkit:dnf) echo "webkitgtk6.0" ;;
        webkit:pacman) echo "webkitgtk-6.0" ;;
        webkit:zypper) echo "typelib-1_0-WebKit-6_0" ;;
        *) ;; # Unknown package manager: no package names to print.
    esac
}

add_required_pkgs() {
    local pkg
    for pkg in $1; do
        REQUIRED_PKGS+=("$pkg")
    done
}

add_optional_pkgs() {
    local pkg
    for pkg in $1; do
        OPTIONAL_PKGS+=("$pkg")
    done
}

check_deps() {
    local python_bin=""
    if [ -x /usr/bin/python3 ]; then
        python_bin="/usr/bin/python3"
    elif command -v python3 >/dev/null 2>&1; then
        python_bin="$(command -v python3)"
    fi

    detect_pm

    echo "Space Previewer dependency check"
    echo

    if [ -z "$python_bin" ]; then
        echo "  missing  python3"
        MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
        add_required_pkgs "$(pkg_for python3 "$PM")"
    else
        echo "  ok       python3"
    fi

    # Module helpers return 0 only when the import succeeds.
    py_module_ok() {
        "$python_bin" -c "import $1" >/dev/null 2>&1
    }

    gi_module_ok() {
        "$python_bin" -c \
            "import gi; gi.require_version('$1', '$2'); from gi.repository import $1" \
            >/dev/null 2>&1
    }

    check_item() {
        local key="$1" label="$2" required="$3"
        local ok=1

        if [ -n "$python_bin" ]; then
            case "$key" in
                gi) py_module_ok gi && ok=0 ;;
                pygments) py_module_ok pygments && ok=0 ;;
                markdown_it) py_module_ok markdown_it && ok=0 ;;
                cairo) py_module_ok cairo && ok=0 ;;
                gtk) gi_module_ok Gtk 4.0 && ok=0 ;;
                adw) gi_module_ok Adw 1 && ok=0 ;;
                gdkpixbuf) gi_module_ok GdkPixbuf 2.0 && ok=0 ;;
                pango) gi_module_ok Pango 1.0 && ok=0 ;;
                poppler) gi_module_ok Poppler 0.18 && ok=0 ;;
                webkit) gi_module_ok WebKit 6.0 && ok=0 ;;
            esac
        fi

        if [ "$ok" -eq 0 ]; then
            echo "  ok       $label"
            return 0
        fi

        if [ "$required" = "required" ]; then
            echo "  missing  $label"
            MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
            add_required_pkgs "$(pkg_for "$key" "$PM")"
        else
            echo "  optional $label (not installed)"
            MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
            add_optional_pkgs "$(pkg_for "$key" "$PM")"
        fi
    }

    check_item gi "gi (PyGObject)" required
    check_item pygments "pygments" required
    check_item markdown_it "markdown_it" required
    check_item cairo "cairo (pycairo)" required
    check_item gtk "Gtk 4.0" required
    check_item adw "Adw 1" required
    check_item gdkpixbuf "GdkPixbuf 2.0" required
    check_item pango "Pango 1.0" required
    check_item poppler "Poppler 0.18" required
    check_item webkit "WebKit 6.0" optional

    echo

    if [ "$MISSING_REQUIRED" -gt 0 ]; then
        if [ -n "$PM" ] && [ "${#REQUIRED_PKGS[@]}" -gt 0 ]; then
            echo "Install the missing dependencies with:"
            echo "  $(install_cmd "$PM") ${REQUIRED_PKGS[*]}"
        else
            echo "Install the missing dependencies with your distro package manager."
        fi
        return 1
    fi

    echo "All required dependencies are installed."

    if [ "$MISSING_OPTIONAL" -gt 0 ]; then
        if [ -n "$PM" ] && [ "${#OPTIONAL_PKGS[@]}" -gt 0 ]; then
            echo "Optional HTML preview support:"
            echo "  $(install_cmd "$PM") ${OPTIONAL_PKGS[*]}"
        fi
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------

stop_legacy_unit() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user stop space-previewer.service >/dev/null 2>&1 || true
        systemctl --user disable space-previewer.service >/dev/null 2>&1 || true
    fi
    if [ -e "$LEGACY_UNIT" ]; then
        echo "==> Removing legacy systemd user unit..."
        rm -f "$LEGACY_UNIT"
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi
}

release_previewer_name() {
    local owner=""

    # A previous copy of this app may still hold the name. Ask it to close and
    # stop it so the freshly installed files are used on the next activation.
    if command -v pkill >/dev/null 2>&1; then
        pkill -f "$APP_INSTALL_DIR/main.py" >/dev/null 2>&1 || true
    fi

    command -v gdbus >/dev/null 2>&1 || return 0

    owner="$(gdbus call --session \
        --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.GetNameOwner \
        "$DBUS_NAME" 2>/dev/null || true)"

    # dconf-style output is (':1.42',); an unowned name raises an error, which
    # the "|| true" above turns into an empty string.
    if [ -z "$owner" ] || [ "$owner" = "()" ]; then
        return 0
    fi

    echo "==> Asking the current owner of $DBUS_NAME to close..."
    gdbus call --session \
        --dest "$DBUS_NAME" \
        --object-path "$DBUS_PATH" \
        --method "$DBUS_NAME.Close" \
        >/dev/null 2>&1 || true

    # Sushi is the common owner. Terminating it is best-effort only: a failure
    # here must never abort the install.
    if command -v pkill >/dev/null 2>&1; then
        pkill -x sushi >/dev/null 2>&1 || true
    fi
}

install_files() {
    echo "==> Installing application files to $APP_INSTALL_DIR..."
    mkdir -p "$APP_INSTALL_DIR"

    # Preserve the src/ layout so installed main.py stays at the top level and
    # utils/i18n.py finds ../locale.
    cp -R "$PROJECT_DIR/src/." "$APP_INSTALL_DIR/"

    # Never ship bytecode caches.
    find "$APP_INSTALL_DIR" -type d -name __pycache__ -prune \
        -exec rm -rf {} + 2>/dev/null || true
    find "$APP_INSTALL_DIR" -name '*.pyc' -delete 2>/dev/null || true

    chmod +x "$APP_INSTALL_DIR/main.py"

    mkdir -p "$APP_INSTALL_DIR/po"
    cp -R "$PROJECT_DIR/po/." "$APP_INSTALL_DIR/po/"

    if [ -f "$PROJECT_DIR/assets/logo-512.png" ]; then
        mkdir -p "$HOME/.local/share/icons/hicolor/512x512/apps"
        cp -f "$PROJECT_DIR/assets/logo-512.png" \
            "$HOME/.local/share/icons/hicolor/512x512/apps/space-previewer.png"
    fi
}

compile_po() {
    local po_file="$1" mo_file="$2"

    if command -v msgfmt >/dev/null 2>&1; then
        msgfmt --check --output-file="$mo_file" "$po_file"
        return
    fi

    # gettext is the usual tool, but Ubuntu images often lack it while Babel
    # is already present for the test suite. Compile the same catalog in Python
    # so translations keep working without root.
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
        return
    fi

    return 1
}

build_locales() {
    local locale_dir="$APP_INSTALL_DIR/locale"
    local po_file lang failed=0

    # Rebuild from scratch so removed languages do not leave stale catalogs.
    rm -rf "$locale_dir"
    mkdir -p "$locale_dir"

    for po_file in "$PROJECT_DIR"/po/*.po; do
        [ -e "$po_file" ] || continue
        lang="$(basename "$po_file" .po)"
        mkdir -p "$locale_dir/$lang/LC_MESSAGES"
        if ! compile_po "$po_file" "$locale_dir/$lang/LC_MESSAGES/space-previewer.mo"; then
            echo "WARNING: failed to compile $po_file (install msgfmt or python3-babel)" >&2
            failed=1
        fi
    done

    if [ "$failed" -eq 1 ]; then
        echo "WARNING: translations are missing from the installed copy." >&2
    fi
}

write_dbus_service() {
    echo "==> Registering D-Bus activation service..."
    mkdir -p "$DBUS_SERVICES_DIR"
    cat > "$SERVICE_FILE" <<EOF
[D-BUS Service]
Name=$DBUS_NAME
Exec=/usr/bin/python3 $APP_INSTALL_DIR/main.py
EOF
}

link_binary() {
    echo "==> Linking space-previewer into $BIN_DIR..."
    mkdir -p "$BIN_DIR"
    ln -sfn "$APP_INSTALL_DIR/main.py" "$BIN_DIR/space-previewer"
}

install_desktop_menus() {
    local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    if [[ "$data_dir" != /* ]]; then
        data_dir="$HOME/.local/share"
    fi

    echo "==> Installing Dolphin service menu and Nemo action..."
    python3 "$PROJECT_DIR/scripts/dolphin-service-menu.py" --main-path "$APP_INSTALL_DIR/main.py" >/dev/null

    if [ -f "$PROJECT_DIR/data/space-previewer.nemo_action" ]; then
        mkdir -p "$data_dir/nemo/actions"
        sed "s|Exec=/usr/bin/space-previewer |Exec=/usr/bin/python3 $APP_INSTALL_DIR/main.py |" \
            "$PROJECT_DIR/data/space-previewer.nemo_action" \
            > "$data_dir/nemo/actions/space-previewer.nemo_action"
        chmod 0644 "$data_dir/nemo/actions/space-previewer.nemo_action"
    fi
}

restart_nautilus() {
    if command -v nautilus >/dev/null 2>&1; then
        nautilus -q >/dev/null 2>&1 || true
    fi
}

show_usage() {
    cat <<EOF
Usage: ./install.sh [--check-deps]

  --check-deps   Check Python/GI dependencies and print the distro install
                 command for anything missing. Does not modify the system.
EOF
}

main() {
    case "${1:-}" in
        --check-deps)
            if check_deps; then
                exit 0
            else
                exit 1
            fi
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        "")
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_usage >&2
            exit 2
            ;;
    esac

    echo "==> Installing Space Previewer (D-Bus activated, no root required)..."

    stop_legacy_unit
    release_previewer_name
    install_files
    build_locales
    write_dbus_service
    link_binary
    install_desktop_menus
    restart_nautilus

    echo "==> Space Previewer installed."
    echo "Press Space on any file in Nautilus to preview."
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) echo "Note: $BIN_DIR is not in your PATH; add it to run 'space-previewer'." ;;
    esac
}

main "$@"
