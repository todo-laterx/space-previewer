#!/bin/bash
set -e

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"
BIN_DIR="$HOME/.local/bin"

echo "==> Stopping and uninstalling Space Previewer..."

# 1. Stop and disable systemd user service
systemctl --user stop space-previewer.service 2>/dev/null || true
systemctl --user disable space-previewer.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/space-previewer.service"
systemctl --user daemon-reload

# 2. Remove DBus service file
rm -f "$DBUS_SERVICES_DIR/org.gnome.NautilusPreviewer.service"

# 3. Remove CLI symlink
rm -f "$BIN_DIR/space-previewer"

# 4. Remove installed application files
rm -rf "$HOME/.local/share/space-previewer"

# 5. Restart Nautilus
nautilus -q || true

echo "==> Space Previewer uninstalled successfully."
