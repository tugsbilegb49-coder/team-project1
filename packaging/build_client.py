#!/usr/bin/env python3
"""Build the team-computer app (no Python/Node needed to run it) into packaging/out/.

Windows: packaging/out/WorkTrack/WorkTrack.exe and WorkTrack-windows.zip
macOS:   packaging/out/WorkTrack.app and WorkTrack-macos.zip
Needs: npm (to build the web page) and `pip install pyinstaller tzdata`.
On macOS build outside iCloud-synced folders (e.g. --out /tmp/worktrack): iCloud keeps adding
Finder attributes that break the app's signature.
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*command):
    print('$', ' '.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'packaging' / 'out', help='Output folder')
    out = parser.parse_args().out.resolve()
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('npm is needed to build the web page (dist/).')
    run(npm, 'run', 'build')
    shutil.rmtree(out, ignore_errors=True)
    run(
        sys.executable,
        '-m',
        'PyInstaller',
        str(ROOT / 'packaging' / 'WorkTrack.spec'),
        '--noconfirm',
        '--clean',
        '--distpath',
        str(out),
        '--workpath',
        str(ROOT / 'packaging' / 'build'),
    )
    if sys.platform == 'darwin':
        app = str(out / 'WorkTrack.app')
        # Extended attributes (e.g. from a Desktop folder) block signing. An ad-hoc signature is
        # required for the app to start on Apple Silicon; it is not a Developer ID signature.
        run('/usr/bin/xattr', '-crs', app)  # -s: also the framework symlinks themselves
        run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', app)
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        archive = out / 'WorkTrack-macos.zip'
        # ditto keeps the app bundle's symlinks and permissions intact.
        run('/usr/bin/ditto', '-c', '-k', '--keepParent', str(out / 'WorkTrack.app'), str(archive))
    else:
        name = 'windows' if sys.platform == 'win32' else 'linux'
        archive = Path(shutil.make_archive(str(out / f'WorkTrack-{name}'), 'zip', out, 'WorkTrack'))
    print(f'Built {archive} ({archive.stat().st_size // 1_000_000} MB)', flush=True)


if __name__ == '__main__':
    main()
