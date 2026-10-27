# space-previewer: engineering rules

GTK4/Libadwaita D-Bus previewer for Nautilus. Python 3, no build step.
Read `README.md` for the product, `.kilo/plans/` for the roadmap, `CONTRIBUTING.md` for workflow.

These rules are non-negotiable. A change that violates one is not done, even if it works locally.

## 1. Contract with Nautilus (highest priority)

`src/main.py` owns `DBUS_XML`. Nautilus is the only client; the upstream contract is
`src/nautilus-previewer.c` in GNOME Nautilus. Exact members:

| Member | Signature |
|---|---|
| `ShowFile` | `(s uri, s windowHandle, b closeIfAlreadyShown, s activationToken)` |
| `Close` | `()` |
| `ParentHandle` | property `s`, read |
| `Visible` | property `b`, read |
| `SelectionEvent` | signal `(u direction)` |
| `NavigateTo` | signal `(s uri)`, since GNOME 51 |
| `Rename` | signal `(s uri)`, since GNOME 51 |
| `Trash` | signal `(s uri)`, since GNOME 51 |

Rules:

- Never change a signature without checking Nautilus. `SelectionEvent` is `u`, not `q`.
- Arrow keys inside the preview emit `SelectionEvent`; they do not page files locally.
- `F2` closes the window, waits about 200 ms, then emits `Rename`. `Del` emits `Trash`.
  `O` opens with the default app. `P` toggles play/pause for audio and video.
- Keep the `windowHandle` from the last `ShowFile`, parent the window to it, and emit
  `PropertiesChanged` when it changes. Call `set_startup_id(activationToken)` before presenting.
- `closeIfAlreadyShown` means toggle: if the requested file is already visible, close instead
  of reloading.
- Never declare a member you do not implement, and never implement one the XML does not declare.

## 2. One dispatch path

- `src/viewers/registry.py` is asked first, then the built-in chain in `src/viewers/__init__.py`.
  Do not add a second MIME/content decision inside a viewer.
- Use `detect_mime_type()` and lowercase extensions. Prefer `Gio.content_type_is_a` over string
  equality when a type can have descendants.
- A new file type gets a viewer, a registry entry only if it is external, and a README row.
  Never a special case buried in `window.py`.

## 3. Viewer contract

Every viewer is a `Gtk.Widget` constructed with `(file_path)` and exposes:

| Member | Required | Notes |
|---|---|---|
| `get_desired_size(screen_w, screen_h)` | yes | returns `(width, height)`, clamped by the window |
| `teardown()` | when it owns a resource | stop players, timers, threads, network |
| `get_header_controls()` | optional | at most 3 widgets |
| `get_status_items()` | optional | `(label, value)` pairs, one line only |
| `toggle_search`, `is_search_open`, `close_search` | optional | text-like viewers only |

- Viewers never resize or close the window; `PreviewWindow` owns layout and lifecycle.
- Viewers never emit D-Bus signals; `PreviewWindow` and `main.py` own the contract.
- No viewer reads the file synchronously on the main thread above 1 MB.

## 4. Resource lifecycle

- `load_file()` calls `teardown()` on the previous viewer before creating the next one.
  Skipping this leaks GStreamer pipelines, WebKit processes, threads and timers.
- Every async load takes a `Gio.Cancellable` and a generation counter. Changing files cancels
  the previous load; a result from an older generation is discarded.
- Timers, threads and network requests are cancelled in `teardown()`.
- Pause a media player before replacing it; preserve pause state across `update_file()`.
- Present the window only when the first render is ready; never resize after presenting.

## 5. Untrusted input limits

Files come from arbitrary sources. These caps are part of the contract:

| Input | Limit |
|---|---|
| Text | 5 MB read, highlight only the first 1 MB |
| Markdown | 2 MB |
| Office (zip inside docx/xlsx/pptx) | 20 MB per entry, 100 MB total, 2000 entries, reject DOCTYPE |
| Archive | 5000 entries, 200 MB uncompressed, reject encrypted entries |
| PDF | 100 pages by default |
| Image | 50 MP before scaling |
| HTML | remote blocked, file access from file URLs disabled |

Any new parser must state its input cap in code and in `SECURITY.md`.

## 6. UI and motion

- One `Adw.HeaderBar`, one bottom status bar. No per-viewer toolbar row.
- At most 3 viewer controls in the header; extra controls go into a `...` menu.
- Search is a non-grabbing overlay card, shown and hidden instantly. It never reflows content.
- Motion: hover and press 100 ms, content crossfade 120 ms. Nothing above 150 ms.
  Animate only `opacity`, `color`, `background-color`, `transform`. Honour `gtk-enable-animations`.
- One accent family: primary fill `#3867D6` with white text; links and focus rings
  `#2F5FC4` light, `#8AB4FF` dark. Override libadwaita through the `--accent-*` CSS
  variables on `:root`, not only the `@accent_*` named colours. Only for focus, links,
  selection, primary action.
- No pure `#000` or `#fff`, no gradients, no glow, no decorative dots, no emoji in the UI.
- Use symbolic icons from the system theme. No bundled fonts.
- Type, size and metadata appear in the status bar, never duplicated inside content.
- Every viewer provides loading (delayed 150 ms), empty, error and fallback states.

## 7. i18n

- No user-visible English literal outside `_()` or `ngettext()`. This includes buttons, labels,
  tooltips, error text, status items and window titles.
- Do not build sentences by concatenation or f-strings; translate whole strings, use placeholders.
- Update `po/space-previewer.pot` and `po/vi.po` in the same change.
- `format_size` and `format_date` are locale-aware; do not hardcode units or date formats.
- The UI path is checked with `rg 'Gtk.Label\(label="[A-Z]'` and equivalent patterns.

## 8. Security

- No network request without an explicit user action. `mermaid.ink` stays opt-in.
- HTML: remote content blocked by default; `file://` cannot read other files; links open in the
  default browser.
- No `shell=True`, no `eval`, no `pickle`, no `yaml.load` without `SafeLoader`.
- Never `except Exception: pass` silently. Log with `GLib`/`logging` and show a message.
- Plugins run in-process with full user permissions; document this and keep the kill switch.

## 9. Code hygiene

- `python3 -m compileall src` must pass before every commit.
- No `print()` in shipped paths. Use `logging` or `GLib` logging.
- Public functions and non-obvious branches get type hints.
- No new dependency without updating `requirements.txt`, the README matrix and the install check.
- Do not commit `.mo` files, caches or generated PDFs.

## 10. Definition of done

A change is complete only when all of these hold:

1. `python3 -m compileall src` and `pytest -q` pass.
2. `bash -n install.sh uninstall.sh` and `msgfmt --check po/*.po` pass.
3. No hardcoded UI string; `.pot` and `vi.po` updated.
4. Manual matrix: affected viewers on Wayland and X11, light and dark, `en` and `vi`.
5. Keyboard path still works: `Space`, arrows, `Esc`, `Ctrl+F`, `Ctrl+Shift+C`, fullscreen,
   `O`, `P`, and `F2`/`Del` when the viewer is not read-only.
6. Screenshots attached for any visual change.

## 11. Review protocol

Review the change as a whole, not hunk by hunk.

1. Read the entire enclosing function, dispatcher or widget lifecycle around every change.
   A correct line can sit behind an earlier `return` and never run.
2. Trace the state lifecycle: initialization, user interaction, dirty/validation, save,
   post-save state. For UI, walk four journeys: open and immediately act, partial update,
   clear to empty, toggle and revert.
3. Check twin paths: text and markdown search, header and status bar, registry and built-in
   dispatch, Wayland and X11 parenting, `en` and `vi` strings.
4. Record a coverage ledger: every changed file, the line ranges read, and `Clean` or a finding
   ID. No silent sampling.
5. Report each finding with exact file and line, a step-by-step runtime trace, the concrete
   impact, and the fix. Severity: `HIGH` (crash, data loss, contract break), `MED` (wrong or
   stale state, leak, missing cancellation), `LOW` (hygiene, copy, style).
6. No emojis in review output.
