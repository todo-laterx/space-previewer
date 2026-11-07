"""File-manager-independent preview application and window lifecycle."""

import os
import urllib.parse

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio

from integrations import StandaloneIntegration
from window import PreviewWindow


class SpacePreviewerApp(Adw.Application):
    def __init__(self, integration=None):
        integration = integration if integration is not None else StandaloneIntegration()
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if not integration.unique:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=integration.application_id, flags=flags)
        self.integration = integration
        self.integration.app = self
        self.window = None
        self.parent_handle = ""

    def do_dbus_register(self, connection, object_path):
        return self.integration.register(connection, object_path)

    def do_activate(self):
        pass

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            self.show_preview_for_path_or_uri(args[1])
        return 0

    def set_parent_handle(self, handle: str):
        handle = handle or ""
        if handle == self.parent_handle:
            return
        self.parent_handle = handle
        if self.window:
            self.window.set_parent_handle(handle)
        self.integration.parent_handle_changed()

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
                self.integration.release_startup()
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
            self.integration.visible_changed(True)

    def close_preview(self):
        if self.window:
            self.window.close()
            self.window = None
            self.integration.visible_changed(False)

    def on_window_closed(self, win):
        self.window = None
        self.integration.visible_changed(False)
        self.integration.release_startup()
        return False

