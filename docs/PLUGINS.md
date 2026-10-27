# Writing a viewer plugin

Space Previewer asks the plugin registry before its built-in MIME dispatch. A plugin is a
single Python file that declares which files it handles and exposes a `Viewer` class.

Plugins are **imported and executed in-process with your user permissions**. There is no
sandbox and no signature check. Only install plugins you have read. Set
`SPACE_PREVIEWER_PLUGINS=0` to disable every plugin without deleting anything.

## Location and precedence

| Directory | Purpose |
|---|---|
| `/usr/share/space-previewer/plugins/1` | system plugins, installed by a package |
| `~/.local/share/space-previewer/plugins/1` | user plugins |

The `1` is `PLUGIN_API`. Files are matched in reverse order, so a user plugin with the same
file name as a system plugin replaces it, and user plugins are consulted first. Each file is
imported once per process. A plugin that raises during import or matching is logged and
skipped; it never blocks the built-in viewers.

## Module contract

```python
PLUGIN_API = 1                  # optional; must equal 1 when present
content_types = ["text/x-foo"]  # optional list of MIME types
extensions = [".foo", ".bar"]   # optional list of lowercase extensions
def supports(mime, ext): ...    # optional final predicate

class Viewer:                   # required
    def __init__(self, file_path): ...
```

Matching order:

1. `extensions` (case-insensitive), when present.
2. exact entries in `content_types`.
3. MIME descendants of `content_types` through `Gio.content_type_is_a`.
4. `supports(mime, ext)` for plugins that declare no static metadata.

At least one of `extensions`, `content_types` or `supports` must match, or the plugin is
never selected. Return `False` from `supports` rather than raising.

## Viewer contract

`Viewer(file_path)` must return any `Gtk.Widget`. The window packs it below the header bar.
Optional members are probed with `hasattr`, so expose only what you implement.

| Member | Required | Notes |
|---|---|---|
| `get_desired_size(screen_w, screen_h)` | yes | return `(width, height)`; the window clamps it |
| `teardown()` | when you own a resource | stop players, timers, threads, network requests |
| `get_header_controls()` | optional | at most three widgets, icon buttons with tooltips |
| `get_status_items()` | optional | `(label, value)` pairs for the one-line status bar |
| `toggle_search()`, `is_search_open()`, `close_search()` | optional | text-like viewers only |
| `get_search_widget()` | optional | a search widget the window moves into its overlay card |
| `set_search_state_callback(cb)` | optional | call `cb()` when search opens or closes |
| `set_status_callback(cb)` | optional | call `cb()` when status values change |
| `set_ready_callback(cb)` | optional | call `cb()` after the first render |
| `toggle_playback()` | optional | bound to `P` for media viewers |

Rules the built-in viewers follow and plugins should copy:

- Do not resize, move or close the window. Return your preferred size and let the window
  decide.
- Do not emit D-Bus signals. `PreviewWindow` and `main.py` own the Nautilus contract.
- Never block the main thread above 1 MB. Read large files in a worker thread and return
  through `GLib.idle_add`, with a generation counter so a stale result is discarded.
- Cancel every timer, thread and network request in `teardown()`. The previous viewer is
  torn down before the next file is shown.
- Cap untrusted input. State the cap in your code; a preview is not a converter.
- Wrap user-visible text in `_()` from `utils.i18n` and keep the string in `po/vi.po`.
- Use symbolic icons from the system theme and the shared status bar for metadata.

## Example

Save as `~/.local/share/space-previewer/plugins/1/toml_viewer.py`:

```python
import os
import pprint
import tomllib

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from utils.formatters import format_size
from utils.i18n import _

PLUGIN_API = 1
content_types = ["application/toml"]
extensions = [".toml"]

MAX_BYTES = 2 * 1024 * 1024


class Viewer(Gtk.Box):
    def __init__(self, file_path: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.file_path = file_path
        self._status_callback = None
        self._size_bytes = os.path.getsize(file_path)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        self.append(scrolled)

        label = Gtk.Label()
        label.set_selectable(True)
        label.set_xalign(0)
        label.set_wrap(True)
        label.add_css_class("monospace")
        scrolled.set_child(label)

        with open(file_path, "rb") as handle:
            raw = handle.read(MAX_BYTES)
        if len(raw) >= MAX_BYTES:
            label.set_text(_("This file is too large to preview."))
        else:
            label.set_text(pprint.pformat(tomllib.loads(raw.decode("utf-8"))))

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        return 900, 640

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def get_status_items(self) -> list[tuple[str, str]]:
        return [(_("Size"), format_size(self._size_bytes))]

    def teardown(self) -> None:
        self._status_callback = None
```

Restart the previewer (close the window, which lets the D-Bus process exit) and press
`Space` on a `.toml` file. Errors appear in the journal:

```bash
journalctl --user -f | rg space-previewer
```

## Testing a plugin

1. Check the module imports: `python3 -c "import pathlib; ..."` is not enough, because a
   plugin may depend on `gi`. Run the app instead and watch the log.
2. Verify the header shows at most three controls and the status bar stays on one line.
3. Switch to another file while your viewer is loading; the stale result must be dropped.
4. Remove the plugin and confirm the built-in viewer takes over again.

## Versioning

`PLUGIN_API` changes only when the contract breaks. A plugin that declares a different
value is skipped with a warning instead of being imported. Bump the directory name and the
constant together.
