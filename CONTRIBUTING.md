# Contributing to Space Previewer

Thanks for taking the time to contribute. This project is a GTK4/Libadwaita file previewer with a shared viewer core and pluggable file-manager adapters (Nautilus D-Bus activation, KDE Dolphin service menu, and standalone CLI), so correctness and resource hygiene matter more than novelty.

## Before you start

- Read `README.md` for supported types, distributions, and install steps.
- Read `docs/INTEGRATIONS.md` for the file-manager adapter architecture.
- Read `SECURITY.md` for the parser input limits and network policy.
- For anything larger than a bug fix, open an issue first and describe the user journey.

## Development setup

Runtime dependencies are system packages, not pip packages, because the application runs under `/usr/bin/python3`. Check missing dependencies on your distribution (`apt`, `dnf`, `pacman`) with:

```bash
./install.sh --check-deps
```

On Ubuntu / Debian:
```bash
sudo apt install python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0 \
  gir1.2-poppler-0.18 python3-pygments python3-markdown-it
```

On Fedora:
```bash
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita poppler-glib \
  python3-pygments python3-markdown-it
```

On Arch Linux / Manjaro:
```bash
sudo pacman -S python-gobject python-cairo gtk4 libadwaita poppler-glib \
  python-pygments python-markdown-it
```

Optional HTML viewer package: `gir1.2-webkit-6.0 libwebkitgtk-6.0-4` (`apt`), `webkitgtk6.0` (`dnf`), or `webkitgtk-6.0` (`pacman`).

Run the app in standalone mode without installing the D-Bus service:

```bash
python3 src/main.py --standalone /path/to/a/file
```

Install and uninstall the per-user daemon and CLI:

```bash
./install.sh
./uninstall.sh
```

`install.sh` shadows the Sushi D-Bus service from the user data directory and does not need root. It terminates a running Sushi so the bus name can be taken over.

## Checks before opening a pull request

```bash
python3 -m compileall src
pytest -q
/usr/bin/python3 -m unittest discover -s tests -p 'test_integrations.py' -v
/usr/bin/python3 -m unittest discover -s tests -p 'test_dolphin.py' -v
/usr/bin/python3 -m unittest discover -s tests -p 'test_packages.py' -v
bash -n install.sh uninstall.sh scripts/build-deb.sh scripts/build-appimage.sh scripts/build-rpm.sh scripts/write-checksums.sh
msgfmt --check po/*.po
```

Manual matrix for any viewer change: Wayland and X11, light and dark, `en` and `vi`, plus the
keyboard path (`Space`, arrows, `Esc`, `Ctrl+F`, `F`/`F11`, `O`, `P`, `F2`, `Del`).

## What a good change looks like

- One topic per pull request. Refactors and behavior changes do not share a commit.
- The D-Bus contract in `src/integrations/nautilus.py` is changed only with a matching change in the
  `window.py` handlers and a note about the Nautilus version.
- New viewers implement `get_desired_size(screen_w, screen_h)` and `teardown()`, expose at
  most 3 header controls via `get_header_controls()` and one-line metadata via
  `get_status_items()`, and declare their input limits in code and in `SECURITY.md`.
- Every async path takes a `Gio.Cancellable`. Switching files must cancel in-flight work.
- UI strings go through `_()` / `ngettext()` in the same change as the `.pot` and `vi.po` update.
- No new pip dependency without updating `README.md`, `requirements.txt` and the install check.

## Commit messages

Use an imperative subject under 72 characters, then a short body explaining why.

```
Fix SelectionEvent signature so arrow keys reach Nautilus

The interface declared the direction as q while Nautilus decodes u, so the
signal was dropped. Match the upstream signature and emit Gtk.DirectionType.
```

## Review

Reviews check the change as a whole rather than hunk by hunk: whole-function reading,
state-lifecycle tracing, twin-path parity (Wayland/X11, light/dark, `en`/`vi`), and a
coverage ledger. Expect findings in the form `file:line`, runtime trace, impact, fix.

Reviewers should check correctness first: contract breaks, leaks, missing cancellation,
unbounded parsing, stale state. Style comments come last.

## Plugins

File-manager adapters are separate from viewer plugins; see
[the integration contract](docs/INTEGRATIONS.md). Keep protocol code out of the
preview core and advertise supported actions through adapter capabilities.

Third-party viewers live in `~/.local/share/space-previewer/plugins/1` and run in-process
with full user permissions. There is no sandbox. The module and viewer contract, matching
order, lifecycle rules and a worked example are in [docs/PLUGINS.md](docs/PLUGINS.md).
Document the trust boundary in the plugin README and keep the
`SPACE_PREVIEWER_PLUGINS=0` escape hatch working.

## Licensing

By contributing you agree that your work is licensed under GPL-3.0, the license of this
repository.
