"""Nautilus D-Bus protocol adapter, including its legacy interface."""

import logging
import os

from gi.repository import Gio, GLib

from . import StandaloneIntegration

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


class NautilusIntegration(StandaloneIntegration):
    application_id = "org.gnome.NautilusPreviewer"
    unique = True
    capabilities = frozenset({"select", "rename", "trash"})

    def __init__(self):
        super().__init__()
        self.dbus_conn = None
        self._startup_hold = False
        self._idle_release_id = 0
        self._filter_id = 0
        self.node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_XML)

    def normalize_incoming_message(self, connection, message, incoming):
        if (
            incoming
            and message.get_message_type() == Gio.DBusMessageType.METHOD_CALL
            and message.get_interface() == PREVIEWER_IFACE
            and message.get_member() == "ShowFile"
            and message.get_signature() == "ssb"
        ):
            body = message.get_body()
            if body is not None:
                uri, window_handle, close_if_already_shown = body.unpack()
                upgraded = message.copy()
                upgraded.set_body(
                    GLib.Variant(
                        "(ssbs)",
                        (uri, window_handle, close_if_already_shown, ""),
                    )
                )
                return upgraded
        return message

    def register(self, connection, object_path):
        self.dbus_conn = connection
        if object_path == OBJECT_PATH:
            if hasattr(connection, "add_filter") and not self._filter_id:
                self._filter_id = connection.add_filter(
                    self.normalize_incoming_message
                )
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
                self.app.hold()
                self._startup_hold = True
                self._idle_release_id = GLib.timeout_add_seconds(
                    30, self._release_if_idle
                )
        return True

    def _release_if_idle(self):
        self._idle_release_id = 0
        if self.app.window is None:
            self.release_startup()
        return False

    def release_startup(self):
        if self._idle_release_id:
            GLib.source_remove(self._idle_release_id)
            self._idle_release_id = 0
        if self._startup_hold:
            self._startup_hold = False
            if self.app is not None:
                self.app.release()

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

    def visible_changed(self, is_visible: bool):
        self._emit_property_changed("Visible", GLib.Variant("b", is_visible))

    def parent_handle_changed(self):
        self._emit_property_changed("ParentHandle", GLib.Variant("s", self.app.parent_handle))

    def handle_dbus_get_property(self, connection, sender, object_path, interface_name, property_name):
        if property_name == "Visible":
            return GLib.Variant('b', bool(self.app.window and self.app.window.get_visible()))
        if property_name == "ParentHandle":
            return GLib.Variant('s', self.app.parent_handle)
        return None

    def handle_dbus_call(
        self, connection, sender, object_path, interface_name, method_name, parameters, invocation
    ):
        if interface_name == PREVIEWER_IFACE:
            if method_name == "ShowFile":
                unpacked = parameters.unpack()
                if len(unpacked) == 3:
                    uri, window_handle, close_if_already_shown = unpacked
                    activation_token = ""
                else:
                    uri, window_handle, close_if_already_shown, activation_token = unpacked
                target_path = self.app.normalize_uri_or_path(uri)
                if (
                    close_if_already_shown
                    and self.app.window
                    and self.app.window.get_visible()
                    and os.path.abspath(self.app.window.current_file_path) == target_path
                ):
                    self.app.close_preview()
                    invocation.return_value(None)
                    return
                self.app.set_parent_handle(window_handle)
                self.app.show_preview_for_path_or_uri(uri, activation_token)
                invocation.return_value(None)
            elif method_name == "Close":
                self.app.close_preview()
                invocation.return_value(None)
        elif interface_name == LEGACY_IFACE:
            if method_name == "ShowFile":
                try:
                    uri = parameters.get_child_value(0).get_string()
                except Exception:
                    uri = parameters.unpack()[0]
                self.app.show_preview_for_path_or_uri(uri)
                invocation.return_value(None)
            elif method_name == "Close":
                self.app.close_preview()
                invocation.return_value(None)

    def select(self, direction: int):
        self._emit_signal("SelectionEvent", GLib.Variant("(u)", (int(direction),)))

    def emit_navigate_to(self, uri: str):
        self._emit_signal("NavigateTo", GLib.Variant("(s)", (uri,)))

    def rename(self, uri: str):
        self._emit_signal("Rename", GLib.Variant("(s)", (uri,)))

    def trash(self, uri: str):
        self._emit_signal("Trash", GLib.Variant("(s)", (uri,)))

