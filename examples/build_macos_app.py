"""Wrap a locally built Rings of Power executable in a Finder-launchable macOS app."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/rings-of-power/rings-of-power')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/RROP.app')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('build the app on macOS')
    binary, output = args.binary.resolve(), args.output.absolute()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error('build the SDL game first with examples/build_rings_of_power.py')
    if output.suffix != '.app' or output.exists():
        parser.error('output must be a new .app path; move the previous app or choose --output')
    try:
        subprocess.run(['otool', '-h', str(binary)], check=True, capture_output=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            app = Path(temporary) / output.name
            contents = app / 'Contents'
            macos = contents / 'MacOS'
            macos.mkdir(parents=True)
            shutil.copy2(binary, macos / 'game')
            with (contents / 'Info.plist').open('wb') as stream:
                plistlib.dump({
                    'CFBundleIdentifier': 'org.rrop.game',
                    'CFBundleName': 'Rings of Power',
                    'CFBundleExecutable': 'launch',
                    'CFBundlePackageType': 'APPL',
                    'CFBundleVersion': '1',
                    'CFBundleShortVersionString': '1.0',
                    'NSHighResolutionCapable': True,
                }, stream)
            launcher = macos / 'launch'
            launcher.write_text('''#!/bin/bash
set -eu
app_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
data="$HOME/Library/Application Support/RROP"
mkdir -p -- "$data"
cd -- "$data"
exec "$app_dir/game" --window --audio on --save-dir "$data/saves" --widescreen --zoom --smooth-camera --mouse "$@" >> "$data/launch.log" 2>&1
''')
            launcher.chmod(0o755)
            subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
            app.rename(output)
        print(output)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
