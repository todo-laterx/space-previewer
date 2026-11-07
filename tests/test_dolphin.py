"""Dolphin menu installation tests; no desktop session is required."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dolphin-service-menu.py"
spec = importlib.util.spec_from_file_location("dolphin_menu", SCRIPT)
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class DolphinMenuTests(unittest.TestCase):
    def test_application_modes_without_display(self):
        result = subprocess.run([sys.executable, '-c', '''
import sys
sys.path.insert(0, 'src')
try:
    from main import create_app
    from gi.repository import Gio
except (ImportError, ValueError):
    sys.exit(77)
app = create_app(standalone=True)
assert app.get_flags() & Gio.ApplicationFlags.NON_UNIQUE
assert app.get_application_id() != 'org.gnome.NautilusPreviewer'
assert app.do_dbus_register(None, '/test')
assert 'integrations.nautilus' not in sys.modules
assert not app.integration.capabilities
normal = create_app()
assert normal.get_application_id() == 'org.gnome.NautilusPreviewer'
assert not normal.get_flags() & Gio.ApplicationFlags.NON_UNIQUE
'''], cwd=ROOT, capture_output=True, text=True)
        if result.returncode == 77:
            self.skipTest('GTK runtime dependencies unavailable')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exec_round_trip(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib unavailable')
        path = '/tmp/a b/100%/quote" dollar$ tick` slash\\/main.py'
        keyfile = GLib.KeyFile()
        rendered = menu.render_menu(path)
        keyfile.load_from_data(rendered, len(rendered.encode('utf-8')), GLib.KeyFileFlags.NONE)
        command = keyfile.get_string('Desktop Action Preview', 'Exec')
        success, argv = GLib.shell_parse_argv(command)
        self.assertTrue(success)
        self.assertEqual(argv[1].replace('%%', '%'), path)
        self.assertEqual(argv[2:], ['--standalone', '%f'])

    def test_exec_escaping(self):
        self.assertEqual(menu.quote_exec_argument('/tmp/a b/100%/main.py'),
                         '"/tmp/a b/100%%/main.py"')
        for char in ('"', '$', '`'):
            self.assertEqual(menu.quote_exec_argument(char), '"' + '\\\\' + char + '"')
        self.assertEqual(menu.quote_exec_argument('\\'), '"' + '\\' * 4 + '"')

    def test_local_single_selection_only(self):
        rendered = menu.render_menu('/tmp/check out/main.py')
        self.assertIn('X-KDE-Protocols=file\n', rendered)
        self.assertIn('X-KDE-RequiredNumberOfUrls=1\n', rendered)
        self.assertIn('Exec=/usr/bin/python3 "/tmp/check out/main.py" --standalone %f\n', rendered)
        self.assertNotIn('@MAIN_PATH@', rendered)

    def test_relative_xdg_data_home_is_ignored(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}):
            self.assertEqual(menu.menu_path(), Path.home() / '.local/share/kio/servicemenus/space-previewer.desktop')

    def test_install_and_idempotent_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='dolphin menu ') as directory:
            env = dict(os.environ, XDG_DATA_HOME=directory)
            target = Path(directory) / 'kio/servicemenus/space-previewer.desktop'
            unrelated = Path(directory) / 'keep.txt'
            unrelated.write_text('keep')
            for _ in range(2):
                subprocess.run([sys.executable, str(SCRIPT)], env=env, check=True, capture_output=True)
                self.assertTrue(target.stat().st_mode & 0o100)
                self.assertEqual(target.read_text(), menu.render_menu(ROOT / 'src/main.py'))
            for _ in range(2):
                subprocess.run([sys.executable, str(SCRIPT), '--uninstall'], env=env, check=True, capture_output=True)
                self.assertFalse(target.exists())
            self.assertEqual(unrelated.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
