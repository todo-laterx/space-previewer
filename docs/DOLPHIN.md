# Dolphin integration

## Scope and plan

This first stage adds a service menu for one local file or folder in Dolphin
(KDE Frameworks 5.85+ / KDE Frameworks 6). It reuses the existing GTK viewers.

1. Add an independent application mode without the Nautilus D-Bus interface.
2. Install a localized service menu pointing at the source checkout.
3. Check command escaping, install/remove behavior, and application isolation.
4. Validate the menu in Dolphin on X11 and Wayland before claiming full desktop support.

A later stage needs investigation of Dolphin's APIs for Space activation,
selection updates, and parent-window/activation handles. Service menus alone
do not provide those events. Remote KIO URLs also need a separate design.

## Install a package

Both packages install the menu at
`/usr/share/kio/servicemenus/space-previewer.desktop`. It runs
`/usr/bin/space-previewer --standalone %f`, independent of the source checkout.
The package manager owns the menu and removes it when the package is removed.
No per-user installation script is required. Reopen Dolphin after installation.

If you previously used the source helper, remove its menu first, because the
per-user menu overrides the system menu with the same name:

```bash
python3 scripts/dolphin-service-menu.py --uninstall
```

On Debian/Ubuntu:

```bash
sudo apt install ./dist/space-previewer_0.1.0_amd64.deb
```

On Fedora:

```bash
sudo dnf install ./dist/space-previewer-0.1.0-1.noarch.rpm
```

Use the filename matching the version you built. Remove with
`sudo apt remove space-previewer` or `sudo dnf remove space-previewer`.
The `.deb` retains the existing Nautilus integration and Sushi service diversion.
The Fedora RPM also installs the Nautilus service. It declares a conflict with
`sushi` because both packages own the same D-Bus service file. Choose one
previewer; DNF must resolve that conflict before installation. Nautilus and
Dolphin are recommended packages, not mandatory dependencies.

## Build and test packages

```bash
bash scripts/build-deb.sh
bash scripts/build-rpm.sh
python3 -m unittest discover -s tests -p 'test_packages.py' -v
```

The Debian builder needs `dpkg-deb` and gettext (or the existing Babel fallback).
On Fedora, install `rpm-build` and `gettext` for the RPM builder. For a cross-build
on a Debian host with `rpm` and `gettext` installed, use
`bash scripts/build-rpm.sh --nodeps`: this bypasses the build-dependency RPM
database check, while preserving the runtime dependencies in the resulting RPM.
The package tests also need `rpm2cpio` and `cpio` to inspect the RPM payload.

Tests build and unpack actual packages in a temporary directory and check the
menu, launcher, file modes, catalogs, dependencies and Nautilus service policy.
They also check RPM file ownership and removal using an isolated database-only
transaction. They do not install packages into the host or verify Fedora
dependency resolution.

## Install from source

Install the runtime dependencies listed in the README. Check them with:

```bash
bash install.sh --check-deps
```

From the checkout, install only the Dolphin menu:

```bash
python3 scripts/dolphin-service-menu.py
```

The helper writes `space-previewer.desktop` under
`${XDG_DATA_HOME:-~/.local/share}/kio/servicemenus/` and marks it executable.
It uses `/usr/bin/python3` and the absolute path to this checkout's `src/main.py`.
Keep the checkout in place; rerun the helper after moving it. This integration
does not require `./install.sh`, replace Sushi, or restart Nautilus.
The helper is for source installs; it does not install a deb/AppImage integration.

Updating or switching branches in this checkout also changes the application
launched by the menu. Keep it on the desired version for everyday use.

The menu's Vietnamese label is included directly in the desktop entry. To also
translate the preview window, compile its catalog from the checkout (requires
`msgfmt`, provided by the `gettext` package):

```bash
mkdir -p locale/vi/LC_MESSAGES
msgfmt --check -o locale/vi/LC_MESSAGES/space-previewer.mo po/vi.po
```

The window follows the session language. To test Vietnamese explicitly:

```bash
SPACE_PREVIEWER_LANG=vi /usr/bin/python3 src/main.py --standalone "$PWD/README.md"
```

Reopen Dolphin, select one local file or folder, and choose **Preview with Space
Previewer** from the context menu (possibly under **Actions**). Check Dolphin's
**Configure Dolphin > Context Menu** settings if the action is hidden.

Each invocation opens an independent window. `Space` and `Escape` close it;
viewer features such as search, zoom, and opening the default application remain
available. Space in Dolphin does not launch the preview. Arrow-key selection
sync, F2 rename, and Delete-to-trash integration are unavailable in this mode.
The window is not attached to a Dolphin parent window. Only local `file` URLs
are offered; SMB/SFTP and other KIO protocols are excluded.

To try the independent mode directly:

```bash
python3 src/main.py --standalone /absolute/path/to/file
```

To remove only the menu (safe to repeat):

```bash
python3 scripts/dolphin-service-menu.py --uninstall
```

## Validation before submitting

- Run the repository checks in `CONTRIBUTING.md` and the Dolphin tests.
- Verify the generated entry in Dolphin. `desktop-file-validate` does not
  understand KDE's `Type=Service` and `all/all` extensions and reports errors
  for these entries, including KDE's own installed service menus.
- On both Wayland and X11, open a local file and folder through Dolphin; test
  spaces, Unicode, percent signs and shell metacharacters in filenames.
- Confirm multiple selections and remote URLs do not offer the action.
- Open and close previews with Sushi/Nautilus running; confirm their D-Bus
  service is unaffected, then verify the original Nautilus workflow.
- Check English/Vietnamese menu labels and uninstall/reinstall.

The contribution guide asks for an issue describing larger features before a
pull request. Link that discussion when submitting this integration.
