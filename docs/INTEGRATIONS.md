# File-manager integrations

The preview application remains GTK4/Libadwaita. File-manager protocols are
adapters, not conditions inside the window or individual viewers.

## Layout

- `src/app.py`: opening, updating and closing previews; generic parent handles.
- `src/window.py` and `src/viewers/`: shared UI and content rendering.
- `src/integrations/__init__.py`: the standalone adapter and lifecycle hooks.
- `src/integrations/nautilus.py`: Nautilus D-Bus interfaces, signals and activation hold.
- `src/main.py`: compatibility entry point selecting an adapter.
- `data/space-previewer.desktop`: Dolphin's service menu invoking `--standalone`.

With no flag, the entry point still selects Nautilus so existing activation files
keep working. `--standalone` selects the independent adapter and does not import
the Nautilus implementation. Constructing `SpacePreviewerApp()` directly also
uses the independent adapter by default.

## Adapter contract

An adapter instance belongs to one application; the core assigns its `app`
reference before registration. Subclass `StandaloneIntegration` and override
only the hooks or capabilities needed:

| Member | Purpose |
| --- | --- |
| `application_id`, `unique` | Application identity and single-instance policy |
| `register(connection, object_path)` | Optional transport registration; return success |
| `visible_changed(visible)` | Notify the caller that a preview opened or closed |
| `parent_handle_changed()` | Notify the caller about a changed parent handle |
| `release_startup()` | Release any activation hold after close or an invalid target |
| `capabilities` | Supported window actions: `select`, `rename`, `trash` |

Each advertised action must have a matching method: `select(direction)`,
`rename(uri)`, or `trash(uri)`. Direction is a GTK direction enum integer; an
adapter translates it if its transport uses a different representation. The
window enables each action and its shortcut independently. Renaming retains
the existing short delay after closing the preview, with an application hold
until the adapter call returns.

Adapters request previews through `app.show_preview_for_path_or_uri()`,
`app.set_parent_handle()` and `app.close_preview()`. They do not implement viewers.
The standalone adapter has no transport or file-manager actions. Dolphin needs
only this adapter plus its declarative service menu, not a separate Python class.

A future Nemo/Thunar integration can use the same CLI for a menu action, or add
an adapter and explicit entry-point selection for richer behavior. Neither is
implemented or advertised as supported yet.

## Refactor scope and validation

The extraction preserves Nautilus's D-Bus names/signatures, command-line flags,
viewers and package behavior. The core has no file-manager-specific imports;
the window checks capabilities instead of standalone/file-manager names.
Packages still bundle the adapters as before. Splitting distro subpackages is
a separate migration because it changes dependency and file-ownership policy.

```bash
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_dolphin.py' -v
python3 -m unittest discover -s tests -p 'test_packages.py' -v
```

Adapter tests need the runtime dependencies but no display or session bus.
They cover D-Bus arguments, signals/properties, activation holds, core lifecycle
and capability-gated actions. Desktop checks on Nautilus and Dolphin remain
necessary after changes to protocol or window behavior.
