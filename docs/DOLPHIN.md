# Dolphin Integration Guide

Space Previewer supports KDE Dolphin (KDE Frameworks 5.85+ and KDE Frameworks 6) through a KIO context-menu action (`Preview with Space Previewer`) that opens any local file or folder in standalone mode (`space-previewer --standalone %f`).

---

## 1. Installing via System Packages (`.deb` / `.rpm`)

Both the Debian/Ubuntu `.deb` package and the Fedora `.rpm` package install the Dolphin service menu automatically at `/usr/share/kio/servicemenus/space-previewer.desktop`.

- The menu runs `/usr/bin/space-previewer --standalone %f`, independent of any source checkout.
- The system package manager owns the menu and removes it cleanly on package removal.
- Reopen Dolphin after installing the package so the new service menu is loaded.

If you previously installed the per-user service menu from a source checkout, remove it first so it does not shadow the system menu:

```bash
python3 scripts/dolphin-service-menu.py --uninstall
```

### Debian / Ubuntu / Kubuntu

```bash
sudo apt install ./dist/space-previewer_0.1.0_amd64.deb
```

Remove with `sudo apt remove space-previewer`. The `.deb` package includes both the Dolphin service menu and the Nautilus D-Bus service (using `dpkg-divert` to coexist cleanly with `gnome-sushi`).

### Fedora / RHEL

```bash
sudo dnf install ./dist/space-previewer-0.1.0-1.noarch.rpm
```

On Fedora Workstation where `sushi` is preinstalled, pass `--allowerasing` so DNF resolves the shared `org.gnome.NautilusPreviewer.service` D-Bus service conflict:

```bash
sudo dnf install --allowerasing ./dist/space-previewer-0.1.0-1.noarch.rpm
```

Remove with `sudo dnf remove space-previewer`. Both `nautilus` and `dolphin` are declared as weak `Recommends:` dependencies rather than mandatory requirements.

---

## 2. Installing from a Source Checkout (No Root Required)

1. Verify that all required GTK4, Libadwaita, and Poppler dependencies are installed:

   ```bash
   bash install.sh --check-deps
   ```

2. Install the per-user Dolphin service menu from the repository root:

   ```bash
   python3 scripts/dolphin-service-menu.py
   ```

   This writes `${XDG_DATA_HOME:-~/.local/share}/kio/servicemenus/space-previewer.desktop`, marks it executable (`0755`), and points it at `/usr/bin/python3` and your checkout's `src/main.py`. Keep the checkout in place (or re-run the script if you move the folder).

3. To compile the Vietnamese UI catalog when running directly from a source checkout:

   ```bash
   mkdir -p locale/vi/LC_MESSAGES
   msgfmt --check -o locale/vi/LC_MESSAGES/space-previewer.mo po/vi.po
   ```

4. To remove the per-user Dolphin service menu:

   ```bash
   python3 scripts/dolphin-service-menu.py --uninstall
   ```

   Running `./uninstall.sh` also removes `${XDG_DATA_HOME:-~/.local/share}/kio/servicemenus/space-previewer.desktop` automatically.

---

## 3. Usage & Behavior in Dolphin

1. Open Dolphin, right-click any single local file or folder, and select **Preview with Space Previewer** (or under the **Actions** submenu, depending on your Dolphin context-menu configuration in **Configure Dolphin > Context Menu**).
2. Each invocation opens an independent preview window (`Gio.ApplicationFlags.NON_UNIQUE`).
3. Press `Space` or `Escape` to close the preview window.
4. All viewer features (rendered Markdown, in-file search with `Ctrl+F`, line/block copy, PDF continuous scrolling, zoom, media playback, and `O` to open in the default application) work identically to Nautilus mode.
5. **Scope of Standalone Mode**:
   - Only single local `file://` items are offered (`X-KDE-Protocols=file`, `X-KDE-RequiredNumberOfUrls=1`); remote KIO protocols (`smb://`, `sftp://`) are excluded.
   - File-manager D-Bus actions specific to Nautilus (arrow-key selection tracking, `F2` rename, and `Delete` to trash) are disabled in standalone mode.

To run standalone mode directly from a terminal on any desktop environment:

```bash
space-previewer --standalone /path/to/file
```

Or from a source checkout:

```bash
python3 src/main.py --standalone /path/to/file
```

---

## 4. Building & Testing Packages

```bash
bash scripts/build-deb.sh
bash scripts/build-rpm.sh
python3 -m unittest discover -s tests -p 'test_dolphin.py' -v
python3 -m unittest discover -s tests -p 'test_packages.py' -v
```

- On Fedora, install `rpm-build` and `gettext` to build the RPM.
- On Debian/Ubuntu hosts with `rpm`, `rpm2cpio`, `cpio`, and `gettext` installed, pass `--nodeps` (`bash scripts/build-rpm.sh --nodeps`) to skip the host RPM build-dependency database check while preserving all runtime `Requires:` and `Recommends:` metadata in the generated `.rpm`.
