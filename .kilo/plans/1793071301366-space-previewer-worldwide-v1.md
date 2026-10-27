# Space Previewer — Worldwide v0.1.0: i18n, Premium UI, HTML + Sushi Parity

## 0. Goal & Positioning

- Product: Nautilus spacebar Quick Look (GTK4/Libadwaita, Python) at `/media/tuannt/Data/DEV/space-previewer`.
- Name: keep repo/app slug **`space-previewer`**, display name **Space Previewer**, app-id **`io.github.<user>.SpacePreviewer`**, tagline **"Quick Look for GNOME"**.
  - Do not use `Peek` (phw/peek, 10.5k-star screen recorder), `SpacePeek` (existing macOS Finder Quick Look extension), `SpaceLook` (same), `Loupe` (GNOME image viewer), `Quick Look` (Apple trademark).
- Positioning: **not** a general Sushi replacement. "Quick preview for the files you actually read: `.md`, code, `.csv`, logs, `.zip`." Sushi parity is the floor so switching is never a downgrade.
- V1 target: worldwide, English default + Vietnamese, system-locale detect, community-translatable later.
- Motion/visual: GTK-native only (CSS transitions, `Gtk.Revealer`, `Gtk.Stack` crossfade). No web-animation libraries or physics.
- Scope V1: DBus contract parity, lifecycle/limits, i18n, new HTML viewer, SVG fix, Office polish, light plugin registry, restyle. Out: epub/ipynb/3D, rich Office rendering, Flathub release, in-preview rename/delete UI (signals only).

Design Read: Linux desktop utility in **Operate** mode for GNOME users, calm Libadwaita-native, neutral zinc surfaces + one desaturated accent.

Dials (app UI, not a landing page): `DESIGN_VARIANCE 3 / MOTION_INTENSITY 2 / VISUAL_DENSITY 5`.

## 1. Market Context (verified 2026-10-27)

Sushi 51.0 shipped 2026-09-11 with a full GTK4/libadwaita/glycin overhaul. Corrected facts:

- **Text/code**: `GtkSourceView` with syntax highlighting, line numbers, Adwaita style schemes, async loader with cancellation. Not "thin".
- **Office**: `libreoffice.js` (LOKDocView) and `libreoffice-pdf.js` → docx/xlsx/pptx with real layout when LibreOffice is installed. Office is **not** a Sushi gap.
- **Folder**: `fallback.js` deep-count (items, total size, inode-based symlink-loop guard, unreadable counting), async.
- **HTML**: WebKit renderer with remote-content blocking + "load once" infobar.
- **File ops**: `F2` rename, `Del` trash, `O` open, `P` play/pause implemented by emitting DBus signals `Rename` / `Trash` / `NavigateTo` to Nautilus.
- **Paging**: arrows in the preview emit `SelectionEvent(u)`; Nautilus moves the selection. This is live, not dead code.
- **Plugin API**: renderer modules loaded from built-in → system → user dirs (`~/.local/share/sushi/plugins-1`), content-type based, user overrides built-in.
- **i18n / packaging**: ~50 locales, distro packages + Flathub + nightly.
- Repo scale: 173 stars (GitHub mirror), 38 stars on GitLab, active 2026-10-26.

Actual differentiators (verified in our code):

- Markdown rendering + offline Cairo mermaid (Sushi shows source only).
- In-file search with match cap, JSON pretty-print, wrap/copy.
- CSV/TSV table grid.
- Archive listing without extraction (zip/tar).
- Folder listing (Sushi has counts only).
- Office text extraction with zero extra dependencies.
- Single-file Python, easy to hack.

Threat: Sushi's plugin API can absorb the markdown/CSV/archive differentiators. Packaging, i18n and sandboxed decoders remain Sushi's structural advantages.

## 2. Confirmed Decisions

1. **Name**: `space-previewer` / "Space Previewer" / `io.github.<user>.SpacePreviewer`. Decide before the first commit (the slug is embedded in install paths, service file, unit name, binary symlink).
2. **DBus**: own `org.gnome.NautilusPreviewer` + `org.gnome.NautilusPreviewer2` through a user service file in `~/.local/share/dbus-1/services` that shadows `/usr/share`. No `sudo`, no package removal. Install only needs to terminate a running Sushi that still owns the name.
3. **Daemon model**: D-Bus activation only. Drop the systemd unit and `hold()`; measure first-press latency and re-add a hold only if it exceeds ~300 ms.
4. **HTML**: WebKitGTK 6.0, remote blocked by default, `Load once` / `Open in browser`, fallback to source view when WebKit is absent.
5. **i18n**: gettext `.po`, `po/LINGUAS` + `po/POTFILES.in`, English default, full Vietnamese, locale-aware sizes/dates, translated `.desktop`/metainfo.
6. **Plugin API**: light Python registry (`PLUGIN_API = 1`), built-in → system → user dirs, user overrides built-in, no sandbox (documented).
7. **Office**: keep stdlib text mode as default. Optional rich view through `soffice --headless --convert-to pdf` + existing Poppler, on demand, cached. Not a default render path.
8. **Scope V1**: HTML + SVG + Office text polish + DBus parity + lifecycle/limits + i18n + plugin registry + restyle. Out: epub/ipynb/STL, rich Office by default, Flathub publishing (spike only), in-preview rename/delete UI.

## 3. Codebase Facts (verified)

- `src/main.py`: DBus XML declares `SelectionEvent` as `q`, while Nautilus/Sushi use **`u`**; `NavigateTo`/`Rename`/`Trash` signals missing; `ParentHandle` returns `""`; `activationToken` is unpacked then ignored; `self.hold()` keeps the process resident.
- `src/window.py`: no viewer teardown; `load_file` is synchronous; `on_open_clicked` builds a URI by string concatenation (breaks on spaces/`#`); shortcuts limited to Space/Esc/Ctrl+F/F/F11.
- Dispatch: if/elif chain in `src/viewers/__init__.py`; `CUSTOM_MIME` maps `.html` but no HTML branch.
- `text_viewer.py`: 5 MB truncation exists; search caps at 2000 matches; Pygments runs on the whole buffer.
- Office viewers use **stdlib `zipfile` + `ElementTree`**, not python-docx/openpyxl/python-pptx; they read up to 50 MB and parse on the main thread.
- `archive_viewer.py`: zip/tar only; README incorrectly claims RAR.
- `image_viewer.py`: `GdkPixbuf.new_from_file` → no animated GIF, no HEIC/AVIF.
- `media_viewer.py`: autoplay, no pause/seek, no teardown on file switch.
- `folder_viewer.py`: first 30 entries only; sums top-level files only; synchronous.
- `markdown_viewer.py`: `mermaid.ink` network call without consent; emoji in alert blocks; hardcoded Catppuccin surfaces.
- Deps: `requirements.txt` = pygments + markdown-it-py; everything else is system GIR. All available in apt on Ubuntu 26.04.
- Repo: zero commits, junk files `B`, `B[Space`, `C[Markdown`, `D[IDE]`, GPL-3.0 LICENSE.

## 4. Tasks

### A. Hygiene + skeleton
1. Delete junk files; `git add` everything including `markdown_viewer.py`; first commit.
2. Add `VERSION` (`0.1.0`), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/PLUGINS.md`, `TRADEMARK.md` (only if a mark/logo is added).
3. `.github/workflows/ci.yml`: `python3 -m compileall src`, `bash -n` both scripts, `msgfmt --check po/*.po`, `pytest -q`, `desktop-file-validate`, `appstreamcli validate`, fail on filenames with spaces/brackets.
4. Rewrite README English-first: positioning vs Sushi with the corrected table, install/uninstall, shortcuts, supported types, per-distro prerequisites, and no false claims (RAR, recursive folder size until implemented).
5. Move app-id to `io.github.<user>.SpacePreviewer` and add `.desktop` + metainfo + icon.

### B. Dependencies + installer
6. Add `deps.py --check` (or `install.sh --check`): import-check `gi`, `pygments`, `markdown_it`, `cairo`; version-check `Gtk 4.0`, `Adw 1`, `Poppler 0.18`; optional `WebKit 6.0`; print the exact distro install line for what is missing. Never `pip install` from the installer.
7. Installer: shadow the Sushi D-Bus service, terminate a running instance, `nautilus -q`, no systemd unit, no root. Idempotent copy + `uninstall.sh` restores cleanly.
8. Document the dependency matrix (section 5). Verify Fedora/Arch package names at implementation time; do not guess.

### C. DBus contract parity (highest priority)
9. Fix `SelectionEvent` arg to `u`; add `NavigateTo(s)`, `Rename(s)`, `Trash(s)` signals and the `ParentHandle` property behaviour.
10. Store `windowHandle` from `ShowFile`, parent the window (`GdkWayland.Toplevel.export_handle` on Wayland, `gdk_x11` foreign window on X11), emit `PropertiesChanged` for `ParentHandle`; ignore gracefully when unsupported.
11. Call `set_startup_id(activationToken)` before presenting; honour `closeIfAlreadyShown` (toggle when the same file is already shown).
12. Actions: `Space`/`Esc`/`q` close; arrows emit `SelectionEvent` with `Gtk.DirectionType`; `O` open in default app; `P` play/pause; `F2` closes then emits `Rename` after ~200 ms; `Del` emits `Trash`; directory + `NavigateTo` for "open folder".

### D. i18n
13. `src/utils/i18n.py` with `gettext.translation("space-previewer", localedir, fallback=True)`, initialised before `Adw.Application`; `SPACE_PREVIEWER_LANG` override.
14. Wrap every UI string with `_()` / `ngettext()`; translatable units and plurals.
15. `po/space-previewer.pot`, `po/en.po`, `po/vi.po`, `po/LINGUAS`, `po/POTFILES.in`; compile to `locale/` at install; never commit `.mo`.
16. Locale-aware `format_size` (unit names + number grouping) and `format_date` (`GLib.DateTime.format("%x %X")`); translate `.desktop`/metainfo names and comments.

### E. HTML viewer
17. `src/viewers/html_viewer.py`: toolbar badge, `Load remote` toggle (off), `Open in browser`, `WebKit2.WebView` with file-access-from-file disabled, ephemeral or cached data manager.
18. Policy: allow `file://`/`data:` + relative local assets; block `http(s)` until toggled; infobar "Remote content blocked / Load once"; links open in the default browser.
19. Fallback to `TextViewer(lang_hint="html")` with a notice when WebKit is missing.
20. Route before generic `text/`; add `get_desired_size`.

### F. SVG + Office
21. SVG: `Gtk.Picture.new_for_filename` (librsvg) → `TextViewer(lang_hint="xml")` fallback; cap rasterisation.
22. Office text mode: encoding fallback, XML/zip limits, consistent meta bar, translatable legacy `.xls`/`.doc` notice. Remove the wrong python-docx/openpyxl/python-pptx task.
23. Optional rich view: `shutil.which("soffice")` → headless convert to PDF → render with the extracted `PdfPageView`; unique `-env:UserInstallation`, timeout, cancellation, `~/.cache/space-previewer/office/<sha1>` cache with cleanup; button-triggered, never the default path.

### G. Lifecycle, performance, safety
24. Viewer protocol: `teardown()`, called before a viewer is replaced; `Gio.Cancellable` + generation counter per load; cancel in-flight work on rapid paging.
25. Async loading for text/markdown/office/archive/folder; "measure then present" to avoid resize flash; spinner delayed ~150 ms.
26. Limits: text 5 MB (highlight ≤1 MB, plain above), markdown ≤2 MB, office entry ≤20 MB / total ≤100 MB / ≤2000 entries / reject DOCTYPE, archive ≤5000 entries / ≤200 MB / reject encrypted, PDF ≤100 pages default, image ≤50 MP before scaling.
27. Fix image zoom to `Ctrl+scroll` only; free pan otherwise; animated GIF via `GdkPixbufAnimationIter` + frame timer honouring `gtk-enable-animations`.
28. Media: pause old player before replacing, keep pause/seek across `update_file`; optional `P` shortcut.

### H. Plugin registry
29. `src/viewers/base.py` (duck-typed protocol: `content_types`, `extensions`, `supports(mime, ext)`, `get_desired_size`, `get_header_controls`, `get_status_items`, `teardown`) and `src/viewers/registry.py` (`PLUGIN_API = 1`, dirs `/usr/share/space-previewer/plugins/1` and `~/.local/share/space-previewer/plugins/1`, later dir overrides earlier, lazy import, per-plugin try/except, `SPACE_PREVIEWER_PLUGINS=0` kill switch).
30. Query the registry before the built-in if/elif chain; built-ins stay where they are in V1. Document that plugins run unsandboxed in-process.

### I. UI + motion
31. Add `src/widgets/status_bar.py` (type badge, metadata, transient state) and a header-control slot in `PreviewWindow`; viewers expose `get_header_controls()` and `get_status_items()`.
32. Remove the per-viewer toolbar rows from `text_viewer.py` and `markdown_viewer.py`; move their controls into the header as icon-only toggles with tooltips. Replace the search row with the non-grabbing overlay card (instant show/hide, `Esc` restores focus).
33. Replace Catppuccin hardcodes with Libadwaita classes + the single accent and the dedicated code surface; light mode follows the system.
34. Remove emoji from UI (`🖼/💡/🛑`), no 3-equal cards, no glow, no gradient text, no decorative dots.
35. Apply the motion spec (section 5.3) including `gtk-enable-animations` handling; add a `Ctrl+?` shortcut window.
36. Screenshots light/dark × en/vi for text/markdown+mermaid/HTML-blocked/image/PDF/folder.

### J. Release
35. `compileall` clean; manual matrix (image/pdf/text/md/html/csv/archive/font/folder/docx/xlsx/pptx × Wayland/X11 × light/dark × en/vi); Space→preview→arrows→Esc; search; fullscreen; open-with-app; F2/Del/O/P; plugin load.
36. Tag `v0.1.0`, GitHub release tarball, no `.deb` until demand. Flathub spike tracked separately (app-id + `--own-name` + autostart).

## 5. UI & Motion (decided)

Design read: Operate mode, keyboard-first, calm Libadwaita-native.

Decisions:

- **Motion level: static, feedback only.** No window open/close animation, no revealers, no stagger, no hover lift, no infinite loops. Content crossfade on file change is the only content animation.
- **Visual direction: Libadwaita native.** System surfaces, hairline separators instead of cards, system icon theme, light/dark follows the system with no in-app override.
- **Accent: electric blue** `#4C8DFF` (light) / `#6EA8FF` (dark), saturation <80%. Used only for focus rings, links, selected rows, and the single primary action. Never decorative.
- **Layout: header + status bar.** One `Adw.HeaderBar` for filename and viewer controls, one bottom status bar for type and metadata. No sub-toolbar row.

### 5.1 Window skeleton

- HeaderBar: filename (ellipsized, `title-4` weight) on the start; viewer controls as 32 px icon-only toggle buttons with tooltips on the end; `Open` and fullscreen last.
- Search is a non-grabbing overlay card inside a `Gtk.Overlay`: top-end, 12 px margin, 340-380 px wide, one row, shown and hidden instantly with no fade and no height animation. It never reflows content. `Esc` closes search before the window.
- Header budget: at most 3 viewer controls plus `Open` and fullscreen; extra controls go into a `⋯` menu. PDF page navigation (`‹ 3 / 12 ›`) and image zoom (`100%`, click to reset) live in the status bar, not the header.
- Status bar: `Gtk.Box` with a hairline top border, 30 px tall, `caption` + `dim-label`, one line max:
  - start: type badge (`CODE`, `MARKDOWN`, `PDF`, `CSV`, ...)
  - middle: metadata (`2.4 KB`, `128 lines`, `1920 × 1080`, `12 pages`, `48 items`)
  - end: transient state (`Loading...`, `Calculating...`, `Remote blocked`, zoom level)
- Viewers must not repeat type/size inside their content area.

### 5.2 Per-viewer controls (all in the header)

| Viewer | Header controls |
|---|---|
| Text/code | Find, Wrap, Pretty JSON (JSON only), Copy |
| Markdown/Mermaid | Preview/Raw linked toggle, Copy |
| HTML | Load remote switch, Open in browser |
| Image | Zoom reset, Fit toggle |
| Media | Play/Pause, Mute |
| Folder | Recalculate size |
| Office | Text/Layout toggle (layout only when `soffice` exists) |

Language/type badges move to the status bar. Controls stay icon-only; labels live in tooltips and the `Ctrl+?` shortcut window.

### 5.3 Motion spec

- Durations: hover `100 ms`, press `100 ms`, content crossfade `120 ms`. Nothing above 150 ms. Search shows and hides instantly.
- Easing: `cubic-bezier(0.23, 1, 0.32, 1)` for enter, `ease-out` for color/opacity. Never `ease-in`.
- Only animate `opacity`, `background-color`, `color`, and `transform`. Never `margin`, `padding`, `width`, `height`.
- `:active { transform: scale(0.98) }` on pressable controls; no `scale(0)` entrances.
- Honour `gtk-enable-animations`: when false, all durations become 0.
- Crossfade only between file contents, never on window open, search open, or toolbar state.

### 5.4 Tokens and color

- Surfaces come from Libadwaita; no hardcoded window/header colors.
- Dedicated code surface: `#F6F6F7` light / `#1C1C1E` dark, text `#1F2328` / `#E6E6E6`. The only place with its own background.
- One accent variable (5.x above). Errors use the system destructive red, and only for errors.
- No pure `#000` or `#fff`, no gradients, no glow.
- Contrast: body AA 4.5:1, large text 3:1; verify both themes.

### 5.5 Typography

- UI: inherit the system UI font (Adwaita Sans/Cantarell); use Libadwaita classes (`title-4`, `body`, `caption`, `dim-label`) instead of custom sizes.
- Code: system monospace stack (`Adwaita Mono`, `JetBrains Mono`, `Source Code Pro`, `monospace`). No bundled fonts.
- Tabular numerals for sizes, counts, dimensions, and line numbers.
- Markdown reading column capped at 72ch, left-aligned, never centered.

### 5.6 Icons and states

- Symbolic icons only, from the system theme; no emoji, no decorative dots, no three-equal-card layouts.
- Loading: delayed 150 ms spinner in the status bar; previous content stays until the new one is ready (no flash, no centered overlay).
- Empty: symbolic icon + one plain sentence + the action hint.
- Error: inline in the content area with a short cause; never a modal dialog.
- Toast only for destructive feedback (`Trash`).

## 6. Dependency Matrix

| Need | Ubuntu/Debian | Fedora | Arch |
|---|---|---|---|
| GTK4 | `gir1.2-gtk-4.0` | `gtk4` | `gtk4` |
| Libadwaita | `gir1.2-adw-1` | `libadwaita` | `libadwaita` |
| Python GI | `python3-gi` | `python3-gobject` | `python-gobject` |
| Cairo | `python3-cairo`, `python3-gi-cairo` | `python3-cairo` | `python-cairo` |
| Pango | `gir1.2-pango-1.0` | `pango` | `pango` |
| GdkPixbuf | `gir1.2-gdkpixbuf-2.0` | `gdk-pixbuf2` | `gdk-pixbuf2` |
| Poppler | `gir1.2-poppler-0.18` | `poppler-glib` | `poppler-glib` |
| Pygments | `python3-pygments` | `python3-pygments` | `python-pygments` |
| markdown-it | `python3-markdown-it` | `python3-markdown-it` | `python-markdown-it` |
| WebKit 6.0 (optional) | `gir1.2-webkit-6.0`, `libwebkitgtk-6.0-4` | `webkitgtk6.0` | `webkitgtk-6.0` |

Sizes: WebKit ≈ 125 MB installed; LibreOffice for rich Office ≈ 303 MB (43 packages, `--no-install-recommends`); python-docx + openpyxl + lxml ≈ 9 MB and still text-only.

## 7. File Map

- Create: `src/viewers/html_viewer.py`, `src/viewers/base.py`, `src/viewers/registry.py`, `src/widgets/status_bar.py`, `src/utils/i18n.py`, `po/space-previewer.pot`, `po/en.po`, `po/vi.po`, `po/LINGUAS`, `po/POTFILES.in`, `VERSION`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/PLUGINS.md`, `tests/`, `.github/workflows/ci.yml`, `data/*.desktop`, `data/*.metainfo.xml`, `data/icons/`.
- Edit: `src/main.py`, `src/window.py`, `src/viewers/__init__.py`, `src/utils/mime_detector.py`, `src/utils/formatters.py`, all `src/viewers/*_viewer.py`, `install.sh`, `uninstall.sh`, `requirements.txt`, `README.md`, `.gitignore` (`locale/`, `*.mo`).
- Delete: `B`, `B[Space`, `C[Markdown`, `D[IDE]`.
- Do not touch: `.git/` internals, `LICENSE` (GPL-3.0).

## 8. Validation & Risks

- Validation: `compileall` clean; `msgfmt --check` clean; `bash -n` clean; no hardcoded English in the UI path; HTML local renders / remote blocked / `Load once` / fallback; arrows from the preview move Nautilus selection; preview is transient to its parent; F2/Del/O/P work; folder size async <2 s; GIF animates; light+dark AA; one header row + one status bar (no per-viewer toolbar); all transitions ≤150 ms; `gtk-enable-animations=false` yields static UI; no emoji in UI; type badge never duplicated inside content.
- Risks:
  - Sushi's plugin API absorbs markdown/CSV/archive → keep depth (mermaid, search) rather than breadth.
  - Python startup latency after dropping `hold()` → measure, re-add if needed.
  - WebKit package naming drift → feature detection + per-distro table.
  - Office fidelity gap vs LOKDocView → text mode is the honest default, rich view is opt-in.
  - `org.gnome.*` is only a bus name; app-id must stay `io.github.*` for Flathub.
  - Unsandboxed Python plugins → documented, opt-out env var.
