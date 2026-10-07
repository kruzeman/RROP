"""Exercise local app packaging with a synthetic executable, never a ROM."""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'macOS app packaging')
class MacOSApp(unittest.TestCase):
    def test_bundle_with_spaces_and_existing_output_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'demo.c'
            source.write_text('int main(void) { return 0; }\n')
            binary = root / 'demo game'
            subprocess.run(['cc', str(source), '-o', str(binary)], check=True)
            app = root / 'Game with spaces.app'
            command = [sys.executable, str(ROOT / 'examples/build_macos_app.py'),
                       '--binary', str(binary), '--output', str(app)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            contents = app / 'Contents'
            with (contents / 'Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            self.assertEqual(info['CFBundlePackageType'], 'APPL')
            launcher = contents / 'MacOS' / info['CFBundleExecutable']
            self.assertTrue(launcher.stat().st_mode & 0o111)
            subprocess.run(['bash', '-n', str(launcher)], check=True)
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
            subprocess.run([str(contents / 'MacOS/game')], check=True)
            marker = app / 'keep-me'
            marker.write_text('existing app')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), 'existing app')
            missing = subprocess.run([*command[:2], '--binary', str(root / 'missing'),
                                      '--output', str(root / 'Missing.app')],
                                     capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse((root / 'Missing.app').exists())
