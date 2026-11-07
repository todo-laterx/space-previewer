# Contributing to Space Previewer

Thanks for taking the time to contribute. This project is a GTK4/Libadwaita previewer that
implements the Nautilus preview D-Bus contract, so correctness matters more than novelty.

## Before you start

- Read `README.md` for supported types and install steps.
- Read `SECURITY.md` for the parser input limits and network policy.
- For anything larger than a bug fix, open an issue first and describe the user journey.

## Development setup

Runtime dependencies are system packages, not pip packages, because the daemon runs under
`/usr/bin/python3`:

```bash
sudo apt install python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0 \
  gir1.2-poppler-0.18 python3-pygments python3-markdown-it
```

Optional: `gir1.2-webkit-6.0` and `libwebkitgtk-6.0-4` for the HTML viewer.
Per-distro names are in the README matrix.

Run the app without installing the daemon:

```bash
python3 src/main.py /path/to/a/file
```

Install and uninstall the daemon:

```bash
./install.sh
./uninstall.sh
```

`install.sh` shadows the Sushi D-Bus service from the user data directory and does not need
root. It terminates a running Sushi so the bus name can be taken over.

## Checks before opening a pull request

```bash
python3 -m compileall src
pytest -q
bash -n install.sh uninstall.sh
msgfmt --check po/*.po
```

Manual matrix for any viewer change: Wayland and X11, light and dark, `en` and `vi`, plus the
keyboard path (`Space`, arrows, `Esc`, `Ctrl+F`, `F`/`F11`, `O`, `P`, `F2`, `Del`).

## What a good change looks like

- One topic per pull request. Refactors and behavior changes do not share a commit.
- The D-Bus contract in `src/main.py` is changed only with a matching change in the
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

Third-party viewers live in `~/.local/share/space-previewer/plugins/1` and run in-process
with full user permissions. There is no sandbox. The module and viewer contract, matching
order, lifecycle rules and a worked example are in [docs/PLUGINS.md](docs/PLUGINS.md).
Document the trust boundary in the plugin README and keep the
`SPACE_PREVIEWER_PLUGINS=0` escape hatch working.

## Licensing

By contributing you agree that your work is licensed under GPL-3.0, the license of this
repository.
