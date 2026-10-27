import os
import subprocess
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from viewers import create_viewer_for_file

class PreviewWindow(Adw.ApplicationWindow):
    def __init__(self, app, file_path: str):
        super().__init__(application=app)
        self.set_title("Quick Look")
        self.set_default_size(1180, 780)
        self.set_resizable(True)

        self.current_file_path = file_path
        self.current_viewer = None

        # Main Box
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self.main_box)

        # HeaderBar
        self.header_bar = Adw.HeaderBar()
        self.main_box.append(self.header_bar)

        # Open in default app button
        self.btn_open = Gtk.Button(label="Open with App")
        self.btn_open.add_css_class("suggested-action")
        self.btn_open.connect("clicked", self.on_open_clicked)
        self.header_bar.pack_end(self.btn_open)

        # Fullscreen button
        self.btn_fullscreen = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        self.btn_fullscreen.connect("clicked", self.on_fullscreen_toggle)
        self.header_bar.pack_end(self.btn_fullscreen)

        # Content container
        self.viewer_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.viewer_container.set_hexpand(True)
        self.viewer_container.set_vexpand(True)
        self.main_box.append(self.viewer_container)

        # Keyboard controller for Space and Escape
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        # Load file
        self.load_file(file_path)

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
                print(f"[PreviewWindow] Error calculating desired size: {e}")
                target_w, target_h = 1180, 780

        # Safety boundaries
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

        # Clear previous viewer
        child = self.viewer_container.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            self.viewer_container.remove(child)
            child = next_c

        # Create new viewer
        viewer = create_viewer_for_file(self.current_file_path)
        self.current_viewer = viewer
        self.viewer_container.append(viewer)

        # Calculate & apply responsive window height according to content
        self.apply_responsive_size()

    def raise_to_front(self):
        """Present window without unmapping to avoid Wayland stack assertion errors."""
        self.present()

    def update_file(self, file_path: str):
        """Update preview to a new file (when user presses arrow keys in Nautilus)."""
        if os.path.abspath(file_path) != self.current_file_path:
            self.load_file(file_path)
        self.raise_to_front()

    def on_open_clicked(self, btn):
        if self.current_file_path and os.path.exists(self.current_file_path):
            Gio.AppInfo.launch_default_for_uri(f"file://{self.current_file_path}", None)
            self.close()

    def on_fullscreen_toggle(self, btn):
        if self.is_fullscreen():
            self.unfullscreen()
            self.btn_fullscreen.set_icon_name("view-fullscreen-symbolic")
        else:
            self.fullscreen()
            self.btn_fullscreen.set_icon_name("view-restore-symbolic")

    def on_key_pressed(self, controller, keyval, keycode, state):
        is_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        is_alt = bool(state & Gdk.ModifierType.ALT_MASK)
        is_super = bool(state & Gdk.ModifierType.SUPER_MASK)

        # 1. Ctrl + F: In-file Search
        if is_ctrl and not is_alt and not is_super and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            if self.current_viewer and hasattr(self.current_viewer, "toggle_search"):
                self.current_viewer.toggle_search()
                return True
            return False

        # 2. Escape: Close search first if open, else close preview window
        if keyval == Gdk.KEY_Escape:
            if self.current_viewer and hasattr(self.current_viewer, "is_search_open") and self.current_viewer.is_search_open():
                self.current_viewer.close_search()
                return True
            self.close()
            return True

        # 3. Space: Close window (only when not typing inside an editable field)
        if keyval == Gdk.KEY_space:
            focus_widget = self.get_focus()
            if isinstance(focus_widget, Gtk.Editable):
                return False
            self.close()
            return True

        # 4. F or F11: Fullscreen toggle
        # Only toggle on 'F' if NO Ctrl/Alt/Super modifiers and not typing in text field
        if keyval == Gdk.KEY_F11:
            self.on_fullscreen_toggle(None)
            return True

        if not is_ctrl and not is_alt and not is_super and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            focus_widget = self.get_focus()
            if isinstance(focus_widget, Gtk.Editable):
                return False
            self.on_fullscreen_toggle(None)
            return True

        return False
