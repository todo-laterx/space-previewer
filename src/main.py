#!/usr/bin/env python3
import logging
import os
import sys
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from window import PreviewWindow

log = logging.getLogger(__name__)

OBJECT_PATH = "/org/gnome/NautilusPreviewer"
PREVIEWER_IFACE = "org.gnome.NautilusPreviewer2"
LEGACY_IFACE = "org.gnome.NautilusPreviewer"

DBUS_XML = """
<node>
  <interface name="org.gnome.NautilusPreviewer2">
    <method name="ShowFile">
      <arg type="s" direction="in" name="uri" />
      <arg type="s" direction="in" name="windowHandle" />
      <arg type="b" direction="in" name="closeIfAlreadyShown" />
      <arg type="s" direction="in" name="activationToken" />
    </method>
    <method name="Close">
    </method>
    <property name="ParentHandle" type="s" access="read" />
    <property name="Visible" type="b" access="read" />
    <signal name="SelectionEvent">
      <arg type="u" name="direction" />
    </signal>
    <signal name="NavigateTo">
      <arg type="s" name="uri" />
    </signal>
    <signal name="Rename">
      <arg type="s" name="uri" />
    </signal>
    <signal name="Trash">
      <arg type="s" name="uri" />
    </signal>
  </interface>
  <interface name="org.gnome.NautilusPreviewer">
    <method name="ShowFile">
      <arg type="s" name="file_uri" direction="in"/>
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
      <arg type="i" name="width" direction="in"/>
      <arg type="i" name="height" direction="in"/>
      <arg type="b" name="close_on_focus_loss" direction="in"/>
    </method>
    <method name="Close">
    </method>
  </interface>
</node>
"""


class SpacePreviewerApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="org.gnome.NautilusPreviewer",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.window = None
        self.dbus_conn = None
        self.parent_handle = ""
        self._startup_hold = False
        self._idle_release_id = 0
        self.node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_XML)

    def do_activate(self):
        pass

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            self.show_preview_for_path_or_uri(args[1])
        return 0

    def do_dbus_register(self, connection, object_path):
        self.dbus_conn = connection
        if object_path == OBJECT_PATH:
            for iface in self.node_info.interfaces:
                connection.register_object(
                    object_path,
                    iface,
                    self.handle_dbus_call,
                    self.handle_dbus_get_property,
                    None,
                )
            # D-Bus activation starts the process before ShowFile arrives. Hold
            # it until the first preview window closes, then let it exit so the
            # daemon does not stay resident between previews.
            if not self._startup_hold:
                self.hold()
                self._startup_hold = True
                self._idle_release_id = GLib.timeout_add_seconds(
                    30, self._release_if_idle
                )
        return True

    def _release_if_idle(self):
        self._idle_release_id = 0
        if self.window is None:
            self._release_startup_hold()
        return False

    def _release_startup_hold(self):
        if self._startup_hold:
            self._startup_hold = False
            self.release()

    def _emit_signal(self, name: str, parameters: GLib.Variant):
        if not self.dbus_conn:
            return
        try:
            self.dbus_conn.emit_signal(None, OBJECT_PATH, PREVIEWER_IFACE, name, parameters)
        except Exception:
            log.debug("Could not emit %s on the session bus", name, exc_info=True)

    def _emit_property_changed(self, name: str, value: GLib.Variant):
        if not self.dbus_conn:
            return
        try:
            changed = GLib.Variant("a{sv}", {name: value})
            self.dbus_conn.emit_signal(
                None,
                OBJECT_PATH,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                GLib.Variant.new_tuple(
                    GLib.Variant("s", PREVIEWER_IFACE),
                    changed,
                    GLib.Variant("as", []),
                ),
            )
        except Exception:
            log.debug("Could not emit PropertiesChanged for %s", name, exc_info=True)

    def emit_visible_changed(self, is_visible: bool):
        self._emit_property_changed("Visible", GLib.Variant("b", is_visible))

    def emit_parent_handle_changed(self):
        self._emit_property_changed("ParentHandle", GLib.Variant("s", self.parent_handle))

    def set_parent_handle(self, handle: str):
        handle = handle or ""
        if handle == self.parent_handle:
            return
        self.parent_handle = handle
        if self.window:
            self.window.set_parent_handle(handle)
        self.emit_parent_handle_changed()

    def handle_dbus_get_property(self, connection, sender, object_path, interface_name, property_name):
        if property_name == "Visible":
            return GLib.Variant('b', bool(self.window and self.window.get_visible()))
        if property_name == "ParentHandle":
            return GLib.Variant('s', self.parent_handle)
        return None

    def handle_dbus_call(
        self, connection, sender, object_path, interface_name, method_name, parameters, invocation
    ):
        if interface_name == PREVIEWER_IFACE:
            if method_name == "ShowFile":
                uri, window_handle, close_if_already_shown, activation_token = parameters.unpack()
                target_path = self.normalize_uri_or_path(uri)
                if (
                    close_if_already_shown
                    and self.window
                    and self.window.get_visible()
                    and os.path.abspath(self.window.current_file_path) == target_path
                ):
                    self.close_preview()
                    invocation.return_value(None)
                    return
                self.set_parent_handle(window_handle)
                self.show_preview_for_path_or_uri(uri, activation_token)
                invocation.return_value(None)
            elif method_name == "Close":
                self.close_preview()
                invocation.return_value(None)
        elif interface_name == LEGACY_IFACE:
            if method_name == "ShowFile":
                try:
                    uri = parameters.get_child_value(0).get_string()
                except Exception:
                    uri = parameters.unpack()[0]
                self.show_preview_for_path_or_uri(uri)
                invocation.return_value(None)
            elif method_name == "Close":
                self.close_preview()
                invocation.return_value(None)

    def normalize_uri_or_path(self, uri_or_path: str) -> str:
        if not uri_or_path:
            return ""
        if uri_or_path.startswith("file://"):
            return urllib.parse.unquote(urllib.parse.urlparse(uri_or_path).path)
        return os.path.abspath(uri_or_path)

    def show_preview_for_path_or_uri(self, uri_or_path: str, activation_token: str = ""):
        file_path = self.normalize_uri_or_path(uri_or_path)
        if not file_path or not os.path.exists(file_path):
            if self.window is None:
                self._release_startup_hold()
            return

        if self.window and self.window.get_visible():
            self.window.update_file(file_path, self.parent_handle, activation_token)
        else:
            self.window = PreviewWindow(
                self,
                file_path,
                parent_handle=self.parent_handle,
                activation_token=activation_token,
            )
            self.window.connect("close-request", self.on_window_closed)
            self.window.present()
            self.emit_visible_changed(True)

    def close_preview(self):
        if self.window:
            self.window.close()
            self.window = None
            self.emit_visible_changed(False)

    def on_window_closed(self, win):
        self.window = None
        self.emit_visible_changed(False)
        self._release_startup_hold()
        return False

    def emit_selection_event(self, direction: int):
        self._emit_signal("SelectionEvent", GLib.Variant("(u)", (int(direction),)))

    def emit_navigate_to(self, uri: str):
        self._emit_signal("NavigateTo", GLib.Variant("(s)", (uri,)))

    def emit_rename(self, uri: str):
        self._emit_signal("Rename", GLib.Variant("(s)", (uri,)))

    def emit_trash(self, uri: str):
        self._emit_signal("Trash", GLib.Variant("(s)", (uri,)))


def main():
    app = SpacePreviewerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
