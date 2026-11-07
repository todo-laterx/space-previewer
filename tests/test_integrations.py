"""Adapter contracts and core lifecycle, without a display or session bus."""

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    from gi.repository import Gio, GLib
    from app import SpacePreviewerApp
    from integrations import StandaloneIntegration
    from integrations.nautilus import NautilusIntegration, OBJECT_PATH, PREVIEWER_IFACE, LEGACY_IFACE
    from window import PreviewWindow
    from gi.repository import Gdk
    from main import parse_arguments
except (ImportError, ValueError):
    HAS_RUNTIME = False
else:
    HAS_RUNTIME = True


@unittest.skipUnless(HAS_RUNTIME, 'GTK runtime dependencies unavailable')
class NautilusTests(unittest.TestCase):
    def setUp(self):
        self.adapter = NautilusIntegration()
        self.app = Mock(window=None, parent_handle='')
        self.app.normalize_uri_or_path.side_effect = os.path.abspath
        self.adapter.app = self.app
        self.connection = Mock()
        self.adapter.dbus_conn = self.connection

    def call(self, method, parameters, interface=None):
        invocation = Mock()
        self.adapter.handle_dbus_call(None, None, OBJECT_PATH,
                                      interface or PREVIEWER_IFACE,
                                      method, parameters, invocation)
        invocation.return_value.assert_called_once_with(None)

    def test_show_forwards_parent_and_activation_token(self):
        self.call('ShowFile', GLib.Variant('(ssbs)', ('/tmp/a b', 'wayland:parent', False, 'token')))
        self.app.set_parent_handle.assert_called_once_with('wayland:parent')
        self.app.show_preview_for_path_or_uri.assert_called_once_with('/tmp/a b', 'token')

    def test_show_supports_three_argument_nautilus_46_signature(self):
        self.call('ShowFile', GLib.Variant('(ssb)', ('file:///tmp/ubuntu2404.txt', 'x11:0x2a', False)))
        self.app.set_parent_handle.assert_called_once_with('x11:0x2a')
        self.app.show_preview_for_path_or_uri.assert_called_once_with('file:///tmp/ubuntu2404.txt', '')

        msg = Gio.DBusMessage.new_method_call(
            'org.gnome.NautilusPreviewer',
            OBJECT_PATH,
            PREVIEWER_IFACE,
            'ShowFile',
        )
        msg.set_body(GLib.Variant('(ssb)', ('file:///tmp/debian12.txt', 'wayland:old', True)))
        upgraded = self.adapter.normalize_incoming_message(None, msg, True)
        self.assertEqual(upgraded.get_signature(), 'ssbs')
        self.assertEqual(
            upgraded.get_body().unpack(),
            ('file:///tmp/debian12.txt', 'wayland:old', True, ''),
        )

    def test_toggle_same_file_closes_but_other_file_updates(self):
        self.app.window = Mock(current_file_path='/tmp/file')
        self.app.window.get_visible.return_value = True
        self.call('ShowFile', GLib.Variant('(ssbs)', ('/tmp/file', '', True, '')))
        self.app.close_preview.assert_called_once()
        self.app.show_preview_for_path_or_uri.assert_not_called()
        self.call('ShowFile', GLib.Variant('(ssbs)', ('/tmp/other', '', True, '')))
        self.app.show_preview_for_path_or_uri.assert_called_once_with('/tmp/other', '')

    def test_legacy_and_close_are_preserved(self):
        self.call('ShowFile', GLib.Variant('(siiiib)', ('file:///tmp/a', 0, 0, 100, 100, True)), LEGACY_IFACE)
        self.app.show_preview_for_path_or_uri.assert_called_once_with('file:///tmp/a')
        for interface in (LEGACY_IFACE, PREVIEWER_IFACE):
            self.call('Close', GLib.Variant('()', ()), interface)
        self.assertEqual(self.app.close_preview.call_count, 2)

    def test_registration_and_startup_hold_are_balanced(self):
        with patch('integrations.nautilus.GLib.timeout_add_seconds', return_value=123):
            self.assertTrue(self.adapter.register(self.connection, OBJECT_PATH))
        interfaces = [call.args[1].name for call in self.connection.register_object.call_args_list]
        self.assertEqual(interfaces, [PREVIEWER_IFACE, LEGACY_IFACE])
        self.app.hold.assert_called_once()
        self.adapter._release_if_idle()
        self.adapter.release_startup()
        self.app.release.assert_called_once()

    def test_idle_timeout_does_not_release_visible_preview(self):
        self.adapter._startup_hold = True
        self.app.window = Mock()
        self.adapter._release_if_idle()
        self.app.release.assert_not_called()
        self.adapter.release_startup()
        self.app.release.assert_called_once()

    def test_early_release_cancels_timeout_once(self):
        self.adapter._idle_release_id = 123
        self.adapter._startup_hold = True
        with patch('integrations.nautilus.GLib.source_remove') as remove:
            self.adapter.release_startup()
            self.adapter.release_startup()
        remove.assert_called_once_with(123)
        self.assertEqual(self.adapter._idle_release_id, 0)
        self.app.release.assert_called_once()

    def test_timeout_does_not_remove_its_own_source(self):
        self.adapter._idle_release_id = 123
        self.adapter._startup_hold = True
        with patch('integrations.nautilus.GLib.source_remove') as remove:
            self.adapter._release_if_idle()
        remove.assert_not_called()
        self.app.release.assert_called_once()

    def test_signals_keep_wire_types(self):
        for action, name, signature, value in (
            ('select', 'SelectionEvent', '(u)', 3),
            ('rename', 'Rename', '(s)', 'file:///tmp/a'),
            ('trash', 'Trash', '(s)', 'file:///tmp/a'),
            ('emit_navigate_to', 'NavigateTo', '(s)', 'file:///tmp/a'),
        ):
            with self.subTest(action=action):
                getattr(self.adapter, action)(value)
                args = self.connection.emit_signal.call_args.args
                self.assertEqual(args[:4], (None, OBJECT_PATH, PREVIEWER_IFACE, name))
                self.assertEqual(args[4].get_type_string(), signature)
                self.assertEqual(args[4].unpack(), (value,))

    def test_properties_follow_core_state(self):
        self.app.parent_handle = 'x11:123'
        self.app.window = Mock()
        self.app.window.get_visible.return_value = True
        for name, expected in (('Visible', True), ('ParentHandle', 'x11:123')):
            value = self.adapter.handle_dbus_get_property(None, None, OBJECT_PATH, PREVIEWER_IFACE, name)
            self.assertEqual(value.unpack(), expected)
        self.adapter.visible_changed(True)
        args = self.connection.emit_signal.call_args.args
        self.assertEqual(args[2:4], ('org.freedesktop.DBus.Properties', 'PropertiesChanged'))
        self.assertEqual(args[4].unpack(), (PREVIEWER_IFACE, {'Visible': True}, []))


@unittest.skipUnless(HAS_RUNTIME, 'GTK runtime dependencies unavailable')
class CoreTests(unittest.TestCase):
    def setUp(self):
        self.integration = StandaloneIntegration()
        self.integration.visible_changed = Mock()
        self.integration.parent_handle_changed = Mock()
        self.integration.release_startup = Mock()
        self.app = SpacePreviewerApp(self.integration)

    def test_cli_flag_and_separator(self):
        cases = (
            (['preview', '--standalone', '/tmp/file'], True, ['preview', '/tmp/file']),
            (['preview', '/tmp/file', '--standalone'], True, ['preview', '/tmp/file']),
            (['preview', '--standalone', '--', '-file.txt'], True, ['preview', '--', '-file.txt']),
            (['preview', '--', '--standalone'], False, ['preview', '--', '--standalone']),
            (['preview', '--standalone', '--', '--standalone'], True, ['preview', '--', '--standalone']),
            (['preview', '/tmp/file'], False, ['preview', '/tmp/file']),
        )
        for argv, enabled, forwarded in cases:
            with self.subTest(argv=argv):
                self.assertEqual(parse_arguments(argv), (enabled, forwarded))

    def test_command_line_skips_separator(self):
        with patch.object(self.app, 'show_preview_for_path_or_uri') as show:
            for argv, target in ((['preview', '--', '-file.txt'], '-file.txt'),
                                 (['preview', '/tmp/file'], '/tmp/file'),
                                 (['preview', '--', '--standalone'], '--standalone')):
                command = Mock()
                command.get_arguments.return_value = argv
                self.assertEqual(self.app.do_command_line(command), 0)
                show.assert_called_with(target)
            show.reset_mock()
            for argv in (['preview'], ['preview', '--']):
                command.get_arguments.return_value = argv
                self.app.do_command_line(command)
            show.assert_not_called()

    def test_f2_propagates_without_rename_capability(self):
        window = Mock(integration=StandaloneIntegration())
        window._focus_is_editable.return_value = False
        self.assertFalse(PreviewWindow.on_key_pressed(window, None, Gdk.KEY_F2, 0, 0))
        window._request_rename.assert_not_called()
        window.integration.capabilities = frozenset({'rename'})
        self.assertTrue(PreviewWindow.on_key_pressed(window, None, Gdk.KEY_F2, 0, 0))
        window._request_rename.assert_called_once()

    def test_core_opens_updates_and_closes_through_hooks(self):
        path = str(Path(__file__).resolve())
        with patch('app.PreviewWindow') as constructor:
            window = constructor.return_value
            self.app.show_preview_for_path_or_uri(path, 'first')
            constructor.assert_called_once_with(self.app, path, parent_handle='', activation_token='first')
            window.present.assert_called_once()
            self.integration.visible_changed.assert_called_with(True)
            self.app.set_parent_handle('wayland:parent')
            window.set_parent_handle.assert_called_once_with('wayland:parent')
            self.integration.parent_handle_changed.assert_called_once()
            window.get_visible.return_value = True
            self.app.show_preview_for_path_or_uri(path, 'second')
            window.update_file.assert_called_once_with(path, 'wayland:parent', 'second')
            self.app.on_window_closed(window)
            self.assertIsNone(self.app.window)
            self.integration.visible_changed.assert_called_with(False)
            self.integration.release_startup.assert_called_once()

    def test_missing_path_releases_startup(self):
        with patch('app.os.path.exists', return_value=False), patch('app.PreviewWindow') as constructor:
            self.app.show_preview_for_path_or_uri('/missing')
            constructor.assert_not_called()
            self.integration.release_startup.assert_called_once()

    def test_actions_are_gated_individually(self):
        adapter = Mock(capabilities=frozenset({'select'}))
        window = SimpleNamespace(integration=adapter)
        self.assertTrue(PreviewWindow._emit_selection(window, 3))
        adapter.select.assert_called_once_with(3)
        # Unsupported rename must return before trying to close a window.
        PreviewWindow._request_rename(window)
        adapter.rename.assert_not_called()
        adapter.capabilities = frozenset()
        self.assertFalse(PreviewWindow._emit_selection(window, 3))

    def test_rename_keeps_application_alive_until_callback(self):
        adapter = Mock(capabilities=frozenset({'rename'}))
        window = Mock(integration=adapter)
        window._current_uri.return_value = 'file:///tmp/a'
        with patch('window.GLib.timeout_add') as timer:
            PreviewWindow._request_rename(window)
        window.app.hold.assert_called_once()
        window.close.assert_called_once()
        window.app.release.assert_not_called()
        timer.call_args.args[1]()
        adapter.rename.assert_called_once_with('file:///tmp/a')
        window.app.release.assert_called_once()


if __name__ == '__main__':
    unittest.main()
