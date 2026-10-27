#!/usr/bin/env python3
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import urllib.parse
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from window import PreviewWindow

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
      <arg type="q" name="direction" />
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
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.window = None
        self.dbus_conn = None
        self.node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_XML)
        # Keep daemon alive to own DBus service for Nautilus
        self.hold()

    def do_activate(self):
        pass

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            file_arg = args[1]
            self.show_preview_for_path_or_uri(file_arg)
        return 0

    def do_dbus_register(self, connection, object_path):
        self.dbus_conn = connection
        if object_path == "/org/gnome/NautilusPreviewer":
            for iface in self.node_info.interfaces:
                connection.register_object(
                    object_path,
                    iface,
                    self.handle_dbus_call,
                    self.handle_dbus_get_property,
                    None
                )
        return True

    def emit_visible_changed(self, is_visible: bool):
        if not self.dbus_conn:
            return
        try:
            changed = GLib.Variant("a{sv}", {"Visible": GLib.Variant("b", is_visible)})
            invalidated = GLib.Variant("as", [])
            self.dbus_conn.emit_signal(
                None,
                "/org/gnome/NautilusPreviewer",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                GLib.Variant.new_tuple(
                    GLib.Variant("s", "org.gnome.NautilusPreviewer2"),
                    changed,
                    invalidated,
                ),
            )
        except Exception:
            pass

    def handle_dbus_get_property(self, connection, sender, object_path, interface_name, property_name):
        if property_name == "Visible":
            is_vis = bool(self.window and self.window.is_visible())
            return GLib.Variant('b', is_vis)
        elif property_name == "ParentHandle":
            return GLib.Variant('s', "")
        return None

    def handle_dbus_call(self, connection, sender, object_path, interface_name, method_name, parameters, invocation):
        if interface_name == "org.gnome.NautilusPreviewer2":
            if method_name == "ShowFile":
                uri, window_handle, close_if_already_shown, activation_token = parameters.unpack()
                target_path = self.normalize_uri_or_path(uri)
                if close_if_already_shown and self.window and self.window.is_visible():
                    if os.path.abspath(self.window.current_file_path) == target_path:
                        self.close_preview()
                        invocation.return_value(None)
                        return
                self.show_preview_for_path_or_uri(uri)
                invocation.return_value(None)
            elif method_name == "Close":
                self.close_preview()
                invocation.return_value(None)
        elif interface_name == "org.gnome.NautilusPreviewer":
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

    def show_preview_for_path_or_uri(self, uri_or_path: str):
        file_path = self.normalize_uri_or_path(uri_or_path)
        if not file_path or not os.path.exists(file_path):
            return

        if self.window and self.window.is_visible():
            self.window.update_file(file_path)
        else:
            self.window = PreviewWindow(self, file_path)
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
        return False

def main():
    app = SpacePreviewerApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
