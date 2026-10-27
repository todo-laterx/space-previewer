#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"
BIN_DIR="$HOME/.local/bin"

APP_INSTALL_DIR="$HOME/.local/share/space-previewer"

echo "==> Setting up Space Previewer Daemon..."

# 1. Setup directories
mkdir -p "$SYSTEMD_USER_DIR"
mkdir -p "$DBUS_SERVICES_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$APP_INSTALL_DIR"

# 2. Copy source files to standard user share location
echo "==> Copying application files to $APP_INSTALL_DIR..."
cp -r "$PROJECT_DIR/src"/* "$APP_INSTALL_DIR/"
chmod +x "$APP_INSTALL_DIR/main.py"

# 3. Create DBus service activation file
cat <<EOF > "$DBUS_SERVICES_DIR/org.gnome.NautilusPreviewer.service"
[D-BUS Service]
Name=org.gnome.NautilusPreviewer
Exec=/usr/bin/python3 $APP_INSTALL_DIR/main.py
SystemdService=space-previewer.service
EOF

# 4. Create systemd user service for background daemon
cat <<EOF > "$SYSTEMD_USER_DIR/space-previewer.service"
[Unit]
Description=Space Previewer Daemon for Nautilus Quick Look
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $APP_INSTALL_DIR/main.py
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

# 5. Create CLI symlink
ln -sf "$APP_INSTALL_DIR/main.py" "$BIN_DIR/space-previewer"

# 6. Reload and start systemd user service
systemctl --user daemon-reload
systemctl --user enable --now space-previewer.service

# 7. Restart Nautilus so it detects the active previewer service
nautilus -q || true

echo "==> Space Previewer is active and running!"
echo "Press Space on any file in Nautilus to preview."
