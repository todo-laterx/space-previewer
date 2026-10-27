import ctypes
import ctypes.util
import logging
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from viewers import create_viewer_for_file
from utils.formatters import format_size
from utils.i18n import _
from widgets.status_bar import StatusBar

try:
    from viewers.base import teardown_viewer
except ImportError:  # the module lands with the plugin registry
    def teardown_viewer(viewer):
        if viewer is not None and hasattr(viewer, "teardown"):
            try:
                viewer.teardown()
            except Exception:
                logging.getLogger(__name__).exception("Viewer teardown failed")

try:
    gi.require_version('GdkWayland', '4.0')
    from gi.repository import GdkWayland
except (ImportError, ValueError):
    GdkWayland = None

try:
    gi.require_version('GdkX11', '4.0')
    from gi.repository import GdkX11
except (ImportError, ValueError):
    GdkX11 = None

log = logging.getLogger(__name__)

RENAME_DELAY_MS = 200

_ACCENT_PROVIDER = None

ACCENT_BG = "#3867D6"
ACCENT_FG = "#FFFFFF"
ACCENT_LIGHT = "#2F5FC4"
ACCENT_DARK = "#8AB4FF"


def _install_accent_css():
    """Apply the single accent to Adwaita widgets instead of the theme accent."""
    global _ACCENT_PROVIDER
    if _ACCENT_PROVIDER is not None:
        return

    display = Gdk.Display.get_default()
    if display is None:
        return

    provider = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    manager = Adw.StyleManager.get_default()

    def apply(*_args):
        accent = ACCENT_DARK if manager.get_dark() else ACCENT_LIGHT
        # libadwaita 1.6+ resolves its accent through CSS custom properties on
        # :root, so overriding the named colours alone is not enough. Define
        # both: older widgets still read the @accent_* names.
        css = (
            f"@define-color accent_bg_color {ACCENT_BG};"
            f" @define-color accent_fg_color {ACCENT_FG};"
            f" @define-color accent_color {accent};"
            " :root {"
            f" --accent-bg-color: {ACCENT_BG};"
            f" --accent-fg-color: {ACCENT_FG};"
            f" --accent-color: {accent};"
            " }"
        )
        try:
            provider.load_from_data(css.encode("utf-8"))
        except Exception:
            log.exception("Could not load the accent stylesheet")

    apply()
    manager.connect("notify::dark", apply)
    _ACCENT_PROVIDER = provider

TYPE_BY_EXT = {
    ".md": "MARKDOWN",
    ".markdown": "MARKDOWN",
    ".mdown": "MARKDOWN",
    ".mkd": "MARKDOWN",
    ".mdx": "MARKDOWN",
    ".mmd": "MERMAID",
    ".mermaid": "MERMAID",
    ".html": "HTML",
    ".htm": "HTML",
    ".xhtml": "HTML",
    ".pdf": "PDF",
    ".csv": "CSV",
    ".tsv": "CSV",
    ".zip": "ARCHIVE",
    ".tar": "ARCHIVE",
    ".gz": "ARCHIVE",
    ".tgz": "ARCHIVE",
    ".bz2": "ARCHIVE",
    ".xz": "ARCHIVE",
    ".ttf": "FONT",
    ".otf": "FONT",
    ".woff": "FONT",
    ".woff2": "FONT",
    ".docx": "DOCX",
    ".doc": "DOC",
    ".xlsx": "XLSX",
    ".xls": "XLS",
    ".pptx": "PPTX",
    ".ppt": "PPT",
}


class PreviewWindow(Adw.ApplicationWindow):
    def __init__(self, app, file_path: str, parent_handle: str = "", activation_token: str = ""):
        super().__init__(application=app)
        self.app = app
        _install_accent_css()
        self.set_title(_("Quick Look"))
        self.set_default_size(1180, 780)
        self.set_resizable(True)

        self.current_file_path = file_path
        self.current_viewer = None
        self.parent_handle = parent_handle or ""
        self.activation_token = activation_token or ""
        self._shortcuts_window = None

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self.main_box)

        self.header_bar = Adw.HeaderBar()
        self.main_box.append(self.header_bar)

        self.header_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.header_controls.set_valign(Gtk.Align.CENTER)

        self.btn_open = Gtk.Button(label=_("Open with App"))
        self.btn_open.add_css_class("suggested-action")
        self.btn_open.connect("clicked", self.on_open_clicked)

        self.btn_fullscreen = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        self.btn_fullscreen.connect("clicked", self.on_fullscreen_toggle)

        # GtkHeaderBar.pack_end prepends, so pack right-to-left to end up with
        # [viewer controls] [Open] [fullscreen] before the window controls.
        self.header_bar.pack_end(self.btn_fullscreen)
        self.header_bar.pack_end(self.btn_open)
        self.header_bar.pack_end(self.header_controls)

        self.overlay = Gtk.Overlay()
        self.viewer_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.viewer_container.set_hexpand(True)
        self.viewer_container.set_vexpand(True)
        self.overlay.set_child(self.viewer_container)

        self.search_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.search_card.add_css_class("card")
        self.search_card.set_halign(Gtk.Align.END)
        self.search_card.set_valign(Gtk.Align.START)
        self.search_card.set_margin_top(12)
        self.search_card.set_margin_end(12)
        self.search_card.set_size_request(380, -1)
        self.search_card.set_visible(False)
        self.overlay.add_overlay(self.search_card)

        self.main_box.append(self.overlay)

        self.status_bar = StatusBar()
        self.main_box.append(self.status_bar)

        key_controller = Gtk.EventControllerKey.new()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        self.connect("realize", self._on_realize)
        self.connect("close-request", self._on_close_request)

        if self.activation_token:
            self.set_startup_id(self.activation_token)

        self.load_file(file_path)

    # ---------------------------------------------------------------- parenting

    def _on_realize(self, *_args):
        self._apply_parent_handle()
        return False

    def set_parent_handle(self, handle: str):
        self.parent_handle = handle or ""
        self._apply_parent_handle()

    def _apply_parent_handle(self):
        handle = self.parent_handle
        surface = self.get_surface()
        if not handle or surface is None:
            return
        try:
            if handle.startswith("wayland:"):
                if GdkWayland is not None and isinstance(surface, GdkWayland.WaylandToplevel):
                    surface.set_transient_for_exported(handle[len("wayland:"):])
            elif handle.startswith("x11:"):
                if GdkX11 is not None and isinstance(surface, GdkX11.X11Surface):
                    self._set_x11_transient(surface.get_xid(), int(handle[4:], 16))
        except Exception:
            log.warning("Could not attach preview to parent window %s", handle, exc_info=True)

    @staticmethod
    def _set_x11_transient(window_xid: int, parent_xid: int):
        library = ctypes.util.find_library("X11")
        if not library:
            return
        x11 = ctypes.CDLL(library)
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = x11.XOpenDisplay(None)
        if not display:
            return
        try:
            x11.XSetTransientForHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
            x11.XSetTransientForHint.restype = ctypes.c_int
            x11.XSetTransientForHint(display, window_xid, parent_xid)
        finally:
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay(display)

    # ------------------------------------------------------------------ layout

    def get_screen_bounds(self):
        display = Gdk.Display.get_default()
        if display:
            monitors = display.get_monitors()
            if monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
                geom = monitor.get_geometry()
                return geom.width, geom.height
        return 1920, 1080

    def apply_responsive_size(self):
        screen_w, screen_h = self.get_screen_bounds()
        target_w, target_h = 1180, 780

        if self.current_viewer and hasattr(self.current_viewer, "get_desired_size"):
            try:
                target_w, target_h = self.current_viewer.get_desired_size(screen_w, screen_h)
            except Exception as e:
                log.warning("Error calculating desired size: %s", e)
                target_w, target_h = 1180, 780

        min_w = 540
        max_w = int(screen_w * 0.90)
        min_h = 360
        max_h = int(screen_h * 0.85)

        target_w = max(min_w, min(max_w, target_w))
        target_h = max(min_h, min(max_h, target_h))

        self.set_default_size(target_w, target_h)

        if self.get_realized() and not self.is_fullscreen():
            self.set_size_request(target_w, target_h)
            GLib.idle_add(lambda: self.set_size_request(-1, -1))

    def load_file(self, file_path: str):
        self.current_file_path = os.path.abspath(file_path)
        filename = os.path.basename(self.current_file_path)
        self.set_title(filename)

        self._clear_search_card()

        if self.current_viewer is not None:
            teardown_viewer(self.current_viewer)
            self.current_viewer = None

        child = self.viewer_container.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            self.viewer_container.remove(child)
            child = next_c

        viewer = create_viewer_for_file(self.current_file_path)
        self.current_viewer = viewer
        self.viewer_container.append(viewer)
        self._install_viewer_chrome(viewer)

        self.apply_responsive_size()

    def update_file(self, file_path: str, parent_handle: str = None, activation_token: str = None):
        if parent_handle is not None and parent_handle != self.parent_handle:
            self.set_parent_handle(parent_handle)

        if activation_token:
            self.activation_token = activation_token
            self.set_startup_id(activation_token)

        if os.path.abspath(file_path) != self.current_file_path:
            self.load_file(file_path)

        self.present()

    # ------------------------------------------------------------- viewer chrome

    def _install_viewer_chrome(self, viewer):
        while self.header_controls.get_first_child() is not None:
            self.header_controls.remove(self.header_controls.get_first_child())

        controls = []
        getter = getattr(viewer, "get_header_controls", None)
        if callable(getter):
            try:
                controls = list(getter() or [])
            except Exception:
                log.exception("Viewer header controls failed")

        for control in controls[:3]:
            if control is not None:
                self.header_controls.append(control)

        self.status_bar.set_type(self._viewer_type())
        self.status_bar.clear_state()

        items = []
        getter = getattr(viewer, "get_status_items", None)
        if callable(getter):
            try:
                items = list(getter() or [])
            except Exception:
                log.exception("Viewer status items failed")
        self.status_bar.set_items(items or self._default_status_items())

        setter = getattr(viewer, "set_search_state_callback", None)
        if callable(setter):
            try:
                setter(self._on_search_state_changed)
            except Exception:
                log.exception("Could not register the search state callback")

        setter = getattr(viewer, "set_status_callback", None)
        if callable(setter):
            try:
                setter(self._refresh_status)
            except Exception:
                log.exception("Could not register the status callback")

        setter = getattr(viewer, "set_ready_callback", None)
        if callable(setter):
            try:
                setter(self._on_viewer_ready)
            except Exception:
                log.exception("Could not register the ready callback")

    def _on_viewer_ready(self):
        # Async viewers finish after the window was sized from an empty shell;
        # re-measure once the real content exists.
        self.apply_responsive_size()

    def _refresh_status(self, *_args):
        viewer = self.current_viewer
        if viewer is None:
            return
        items = []
        getter = getattr(viewer, "get_status_items", None)
        if callable(getter):
            try:
                items = list(getter() or [])
            except Exception:
                log.exception("Viewer status items failed")
        self.status_bar.set_items(items or self._default_status_items())

    def _on_search_state_changed(self, _is_open=None):
        self._sync_search_card()

    def _clear_search_card(self):
        child = self.search_card.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.search_card.remove(child)
            child = next_child
        self.search_card.set_visible(False)

    def _sync_search_card(self):
        viewer = self.current_viewer
        is_open = False
        if viewer is not None and hasattr(viewer, "is_search_open"):
            try:
                is_open = bool(viewer.is_search_open())
            except Exception:
                is_open = False

        if not is_open:
            self.search_card.set_visible(False)
            return

        if self.search_card.get_first_child() is None:
            getter = getattr(viewer, "get_search_widget", None)
            widget = None
            if callable(getter):
                try:
                    widget = getter()
                except Exception:
                    log.exception("Could not build the search widget")
            if widget is not None:
                parent = widget.get_parent()
                if parent is not None:
                    parent.remove(widget)
                self.search_card.append(widget)

        self.search_card.set_visible(True)
        GLib.idle_add(self._focus_search_entry)

    def _focus_search_entry(self):
        box = self.search_card.get_first_child()
        if box is None:
            return False
        entry = box.get_first_child()
        if isinstance(entry, Gtk.Editable):
            entry.grab_focus()
        return False

    def _viewer_type(self) -> str:
        if os.path.isdir(self.current_file_path):
            return _("FOLDER")
        ext = os.path.splitext(self.current_file_path)[1].lower()
        label = TYPE_BY_EXT.get(ext)
        if label:
            return label
        if ext:
            return ext.lstrip(".").upper()[:8]
        return _("FILE")

    def _default_status_items(self) -> list[tuple[str, str]]:
        try:
            size = os.path.getsize(self.current_file_path)
        except OSError:
            return []
        return [(_("Size"), format_size(size))]

    def _on_close_request(self, *_args):
        if self.current_viewer is not None:
            teardown_viewer(self.current_viewer)
            self.current_viewer = None
        return False

    # ---------------------------------------------------------------- shortcuts

    def _focus_is_editable(self) -> bool:
        return isinstance(self.get_focus(), Gtk.Editable)

    def _search_is_open(self) -> bool:
        viewer = self.current_viewer
        return bool(viewer and hasattr(viewer, "is_search_open") and viewer.is_search_open())

    def _current_uri(self) -> str:
        return Gio.File.new_for_path(self.current_file_path).get_uri()

    def _emit_selection(self, direction) -> bool:
        if self.app and hasattr(self.app, "emit_selection_event"):
            self.app.emit_selection_event(int(direction))
            return True
        return False

    def on_key_pressed(self, controller, keyval, keycode, state):
        is_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        is_alt = bool(state & Gdk.ModifierType.ALT_MASK)
        is_super = bool(state & Gdk.ModifierType.SUPER_MASK)
        no_modifiers = not (is_ctrl or is_alt or is_super)

        if is_ctrl and not is_alt and not is_super and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            if self.current_viewer and hasattr(self.current_viewer, "toggle_search"):
                self.current_viewer.toggle_search()
                self._sync_search_card()
                return True
            return False

        if (
            is_ctrl
            and bool(state & Gdk.ModifierType.SHIFT_MASK)
            and not is_alt
            and not is_super
            and keyval in (Gdk.KEY_c, Gdk.KEY_C)
        ):
            if self._focus_is_editable():
                return False
            copier = getattr(self.current_viewer, "copy_selected_lines", None)
            if callable(copier):
                try:
                    if copier(reference=True):
                        return True
                except Exception:
                    log.debug("Could not copy the line range", exc_info=True)
            return False

        if is_ctrl and not is_alt and not is_super and keyval in (
            Gdk.KEY_question,
            Gdk.KEY_slash,
        ):
            self._show_shortcuts()
            return True

        if keyval == Gdk.KEY_Escape:
            if self._search_is_open():
                self.current_viewer.close_search()
                self._sync_search_card()
                return True
            has_lines = getattr(self.current_viewer, "has_line_selection", None)
            clear_lines = getattr(self.current_viewer, "clear_line_selection", None)
            if callable(has_lines) and callable(clear_lines):
                try:
                    if has_lines():
                        clear_lines()
                        return True
                except Exception:
                    log.debug("Could not clear the line selection", exc_info=True)
            self.close()
            return True

        if keyval == Gdk.KEY_space and no_modifiers:
            if self._focus_is_editable():
                return False
            self.close()
            return True

        if keyval == Gdk.KEY_F11 or (keyval in (Gdk.KEY_f, Gdk.KEY_F) and no_modifiers):
            if self._focus_is_editable():
                return False
            self.on_fullscreen_toggle(None)
            return True

        if no_modifiers and keyval in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
            if self._focus_is_editable():
                return False
            method = "previous_page" if keyval == Gdk.KEY_Page_Up else "next_page"
            action = getattr(self.current_viewer, method, None)
            if callable(action):
                try:
                    action()
                    return True
                except Exception:
                    log.debug("Viewer page navigation failed", exc_info=True)
            return False

        if no_modifiers and keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
            if self._focus_is_editable():
                return False
            directions = {
                Gdk.KEY_Left: Gtk.DirectionType.LEFT,
                Gdk.KEY_Right: Gtk.DirectionType.RIGHT,
                Gdk.KEY_Up: Gtk.DirectionType.UP,
                Gdk.KEY_Down: Gtk.DirectionType.DOWN,
            }
            return self._emit_selection(directions[keyval])

        if no_modifiers and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            if self._focus_is_editable():
                return False
            self.on_open_clicked(None)
            return True

        if no_modifiers and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            if self._focus_is_editable() or not self.current_viewer:
                return False
            if hasattr(self.current_viewer, "toggle_playback"):
                self.current_viewer.toggle_playback()
                return True
            return False

        if keyval == Gdk.KEY_F2:
            if self._focus_is_editable():
                return False
            self._request_rename()
            return True

        if keyval == Gdk.KEY_Delete:
            if self._focus_is_editable():
                return False
            if self.app and hasattr(self.app, "emit_trash"):
                self.app.emit_trash(self._current_uri())
            return True

        return False

    def _request_rename(self):
        uri = self._current_uri()
        if not (self.app and hasattr(self.app, "emit_rename")):
            self.close()
            return

        # Closing the last window lets GApplication quit; hold it until the
        # signal is emitted so the 200 ms delay cannot be cut short. Hold
        # before closing, because the close handler releases the startup hold.
        self.app.hold()
        self.close()

        def emit_later():
            try:
                self.app.emit_rename(uri)
            finally:
                self.app.release()
            return False

        GLib.timeout_add(RENAME_DELAY_MS, emit_later)

    # ----------------------------------------------------------------- actions

    def _show_shortcuts(self):
        if self._shortcuts_window is not None:
            self._shortcuts_window.present()
            return

        window = Adw.Window()
        window.set_transient_for(self)
        window.set_modal(True)
        window.set_title(_("Keyboard Shortcuts"))
        window.set_default_size(440, 560)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.append(Adw.HeaderBar())

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.set_margin_top(12)
        listbox.set_margin_bottom(12)
        listbox.set_margin_start(12)
        listbox.set_margin_end(12)

        shortcuts = [
            (_("Close preview"), "space"),
            (_("Close search, then preview"), "Escape"),
            (_("Find in file"), "<Control>f"),
            (_("Next match"), "Return"),
            (_("Previous match"), "<Shift>Return"),
            (_("Move selection in Files (arrow keys)"), "Left"),
            (_("Open with the default app"), "o"),
            (_("Play or pause media"), "p"),
            (_("Toggle fullscreen"), "F11"),
            (_("Rename in Files"), "F2"),
            (_("Move to trash"), "Delete"),
            (_("Show this window"), "<Control>question"),
        ]

        for title, accelerator in shortcuts:
            row = Adw.ActionRow(title=title)
            key = Gtk.ShortcutLabel(accelerator=accelerator)
            key.set_valign(Gtk.Align.CENTER)
            row.add_suffix(key)
            listbox.append(row)

        scrolled.set_child(listbox)
        content.append(scrolled)
        window.set_content(content)
        window.connect("destroy", self._on_shortcuts_destroyed)

        self._shortcuts_window = window
        window.present()

    def _on_shortcuts_destroyed(self, *_args):
        self._shortcuts_window = None

    def on_open_clicked(self, btn):
        if self.current_file_path and os.path.exists(self.current_file_path):
            uri = Gio.File.new_for_path(self.current_file_path).get_uri()
            Gio.AppInfo.launch_default_for_uri(uri, None)
            self.close()

    def on_fullscreen_toggle(self, btn):
        if self.is_fullscreen():
            self.unfullscreen()
            self.btn_fullscreen.set_icon_name("view-fullscreen-symbolic")
        else:
            self.fullscreen()
            self.btn_fullscreen.set_icon_name("view-restore-symbolic")
