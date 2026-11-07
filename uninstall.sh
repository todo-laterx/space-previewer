#!/bin/bash
# Uninstall Space Previewer for the current user.
#
# Only per-user files are removed. System packages, including Sushi, are left
# exactly as they are; the hint at the end explains how to get Sushi back.
set -euo pipefail

DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"
BIN_DIR="$HOME/.local/bin"
APP_INSTALL_DIR="$HOME/.local/share/space-previewer"
LEGACY_UNIT="$HOME/.config/systemd/user/space-previewer.service"

DBUS_NAME="org.gnome.NautilusPreviewer"
DBUS_PATH="/org/gnome/NautilusPreviewer"
SERVICE_FILE="$DBUS_SERVICES_DIR/$DBUS_NAME.service"

stop_running_instance() {
    # D-Bus activation owns the process; ask it to close and stop it so the
    # install directory is not held by a running interpreter. Best-effort.
    if command -v gdbus >/dev/null 2>&1; then
        gdbus call --session \
            --dest "$DBUS_NAME" \
            --object-path "$DBUS_PATH" \
            --method "$DBUS_NAME.Close" \
            >/dev/null 2>&1 || true
    fi
    if command -v pkill >/dev/null 2>&1; then
        pkill -f "$APP_INSTALL_DIR/main.py" >/dev/null 2>&1 || true
    fi
}

remove_legacy_unit() {
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

restart_nautilus() {
    if command -v nautilus >/dev/null 2>&1; then
        nautilus -q >/dev/null 2>&1 || true
    fi
}

remove_dolphin_menu() {
    echo "==> Removing Dolphin service menu..."
    local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    if [[ "$data_dir" != /* ]]; then
        data_dir="$HOME/.local/share"
    fi
    rm -f "$data_dir/kio/servicemenus/space-previewer.desktop"
}

remove_nemo_action() {
    echo "==> Removing Nemo action..."
    local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
    if [[ "$data_dir" != /* ]]; then
        data_dir="$HOME/.local/share"
    fi
    rm -f "$data_dir/nemo/actions/space-previewer.nemo_action"
}

main() {
    echo "==> Uninstalling Space Previewer..."

    stop_running_instance

    echo "==> Removing D-Bus activation service..."
    rm -f "$SERVICE_FILE"

    echo "==> Removing CLI symlink..."
    rm -f "$BIN_DIR/space-previewer"

    remove_dolphin_menu
    remove_nemo_action

    remove_legacy_unit

    echo "==> Removing installed application files..."
    rm -rf "$APP_INSTALL_DIR"
    rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/space-previewer.png"

    restart_nautilus

    echo "==> Space Previewer uninstalled."
    echo "Sushi was not reinstalled; install gnome-sushi from your distro to restore the default GNOME previewer."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
