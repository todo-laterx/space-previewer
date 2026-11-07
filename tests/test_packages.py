"""Build and inspect real packages in a disposable checkout, without root."""

import gettext
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MENU = Path('usr/share/kio/servicemenus/space-previewer.desktop')


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='space-previewer-packages-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir()
        for name in ('src', 'po', 'data', 'assets', 'docs', 'scripts', 'packaging'):
            shutil.copytree(ROOT / name, self.checkout / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('VERSION', 'LICENSE', 'TRADEMARK.md', 'README.md'):
            shutil.copy2(ROOT / name, self.checkout / name)

    def require_tools(self, *names):
        missing = [name for name in names if not shutil.which(name)]
        if missing:
            self.skipTest('Missing package tools: ' + ', '.join(missing))

    def run_command(self, *args, cwd=None):
        result = subprocess.run(args, cwd=cwd or self.checkout,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def check_payload(self, extracted):
        desktop = extracted / MENU
        self.assertEqual(desktop.read_bytes(), (ROOT / 'data/space-previewer.desktop').read_bytes())
        self.assertEqual(desktop.stat().st_mode & 0o777, 0o644)
        desktop_text = desktop.read_text(encoding='utf-8')
        self.assertIn('Exec=/usr/bin/space-previewer --standalone %f\n', desktop_text)
        self.assertIn('Icon=space-previewer\n', desktop_text)
        nemo_action = extracted / 'usr/share/nemo/actions/space-previewer.nemo_action'
        self.assertEqual(nemo_action.read_bytes(), (ROOT / 'data/space-previewer.nemo_action').read_bytes())
        self.assertEqual(nemo_action.stat().st_mode & 0o777, 0o644)
        self.assertTrue((extracted / 'usr/share/icons/hicolor/512x512/apps/space-previewer.png').is_file())
        service = extracted / 'usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service'
        service_text = service.read_text(encoding='utf-8')
        self.assertIn('Name=org.gnome.NautilusPreviewer\n', service_text)
        self.assertIn('Exec=/usr/bin/python3 /usr/share/space-previewer/main.py\n', service_text)
        launcher = extracted / 'usr/bin/space-previewer'
        launcher_text = launcher.read_text(encoding='utf-8')
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
        self.assertIn('exec /usr/bin/python3 /usr/share/space-previewer/main.py "$@"', launcher_text)
        self.assertTrue((extracted / 'usr/share/space-previewer/main.py').is_file())
        for module in ('app.py', 'integrations/__init__.py', 'integrations/nautilus.py', 'utils/parsers.py'):
            self.assertTrue((extracted / 'usr/share/space-previewer' / module).is_file(), module)
        catalog = extracted / 'usr/share/space-previewer/locale/vi/LC_MESSAGES/space-previewer.mo'
        with catalog.open('rb') as handle:
            self.assertTrue(gettext.GNUTranslations(handle)._catalog)
        self.assertFalse(list(extracted.rglob('*.pyc')))
        self.assertNotIn(str(self.checkout), desktop_text + launcher_text)

    def test_deb_payload_and_metadata(self):
        self.require_tools('dpkg-deb', 'msgfmt')
        self.run_command('bash', 'scripts/build-deb.sh')
        self.run_command('sha256sum', '-c', 'SHA256SUMS', cwd=self.checkout / 'dist')
        package, = (self.checkout / 'dist').glob('*.deb')
        extracted = self.root / 'deb'
        self.run_command('dpkg-deb', '-x', str(package), str(extracted))
        self.check_payload(extracted)
        self.assertTrue((extracted / 'usr/share/dbus-1/services/org.gnome.NautilusPreviewer.service').is_file())
        depends = self.run_command('dpkg-deb', '-f', str(package), 'Depends')
        self.assertIn('gir1.2-poppler-0.18', depends)
        self.assertIn('python3-gi', depends)
        control = self.root / 'control'
        self.run_command('dpkg-deb', '-e', str(package), str(control))
        for script in ('preinst', 'postinst', 'postrm'):
            self.run_command('sh', '-n', str(control / script))
            self.assertNotIn('servicemenus', (control / script).read_text(encoding='utf-8'))

    def test_rpm_payload_and_metadata(self):
        self.require_tools('rpmbuild', 'rpm', 'rpm2cpio', 'cpio', 'msgfmt')
        # Debian hosts have no RPM build-dependency database. The actual build
        # still runs msgfmt and rpmbuild; runtime Requires must remain in the RPM.
        self.run_command('bash', 'scripts/build-rpm.sh', '--nodeps')
        self.run_command('sha256sum', '-c', 'SHA256SUMS', cwd=self.checkout / 'dist')
        # Simulate a host-provided bytecompile hook that would fail if invoked.
        # The spec must undefine it, independently of the host's RPM defaults.
        version = (self.checkout / 'VERSION').read_text(encoding='utf-8').strip()
        topdir = self.checkout / 'build/rpm'
        self.run_command('rpmbuild', '-bb', '--nodeps',
                         '--define', f'_topdir {topdir}',
                         '--define', f'_tmppath {topdir}/tmp',
                         '--define', f'app_version {version}',
                         '--define', '__brp_python_bytecompile /bin/false',
                         '--define', '__os_install_post %{?__brp_python_bytecompile}',
                         'packaging/space-previewer.spec')
        package, = (self.checkout / 'dist').glob('*.rpm')
        extracted = self.root / 'rpm'
        extracted.mkdir()
        payload = subprocess.run(['rpm2cpio', str(package)], capture_output=True, check=True)
        result = subprocess.run(['cpio', '-idm', '--quiet', '--no-absolute-filenames'],
                                input=payload.stdout, cwd=extracted, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.check_payload(extracted)
        requires = self.run_command('rpm', '-qp', '--requires', str(package))
        for dependency in ('python3-gobject', 'poppler-glib', 'libadwaita', 'python3-markdown-it'):
            self.assertIn(dependency, requires.splitlines())
        self.assertNotIn('dolphin', requires.splitlines())
        self.assertNotIn('nautilus', requires.splitlines())
        recommends = self.run_command('rpm', '-qp', '--recommends', str(package)).splitlines()
        self.assertIn('nautilus', recommends)
        self.assertIn('dolphin', recommends)
        self.assertIn('sushi', self.run_command('rpm', '-qp', '--conflicts', str(package)).splitlines())
        self.assertEqual(self.run_command('rpm', '-qp', '--qf', '%{ARCH}', str(package)), 'noarch')
        self.assertEqual(self.run_command('rpm', '-qp', '--scripts', str(package)), '')

        # Exercise ownership/removal in a private RPM database only. No files
        # or scripts are installed on the host and no system D-Bus plugin runs.
        database = self.root / 'rpmdb'
        base = ('rpm', '--noplugins', '--nosignature', '--nodigest', '--dbpath', str(database))
        self.run_command(*base, '--initdb')
        self.run_command(*base, '-i', '--justdb', '--ignoresize', '--nodeps',
                         '--noscripts', '--notriggers', str(package))
        owner = self.run_command(*base, '-q', '--whatprovides', '/' + str(MENU))
        self.assertTrue(owner.startswith('space-previewer-'))
        self.run_command(*base, '-e', '--justdb', '--nodeps', '--noscripts',
                         '--notriggers', 'space-previewer')
        self.assertEqual(self.run_command(*base, '-qa'), '')

    def test_checksums_cover_all_package_formats(self):
        dist = self.root / 'dist'
        dist.mkdir()
        self.run_command('bash', 'scripts/write-checksums.sh', str(dist))
        self.assertEqual((dist / 'SHA256SUMS').read_text(encoding='utf-8'), '')
        for filename in ('preview.deb', 'preview.rpm', 'Preview File.AppImage'):
            (dist / filename).write_bytes(filename.encode())
            self.run_command('bash', 'scripts/write-checksums.sh', str(dist))
            lines = (dist / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
            for artifact in dist.iterdir():
                if artifact.name == 'SHA256SUMS':
                    continue
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                self.assertIn(f'{digest}  {artifact.name}', lines)


if __name__ == '__main__':
    unittest.main()
