#!/usr/bin/env python3
"""Build the team-computer app (no Python/Node needed to run it) into packaging/out/.

Windows: packaging/out/WorkTrack/WorkTrack.exe and WorkTrack-windows.zip
macOS:   packaging/out/WorkTrack.app and WorkTrack-macos.zip
Needs: npm (to build the web page) and `pip install pyinstaller tzdata`.
On macOS build outside iCloud-synced folders (e.g. --out /tmp/worktrack): iCloud keeps adding
Finder attributes that break the app's signature.

Signing (optional; without it the app is unsigned on Windows and ad-hoc signed on macOS, so the
first start shows a SmartScreen / Gatekeeper warning). Set these in the environment:

  macOS   MACOS_SIGN_IDENTITY   "Developer ID Application: Company (TEAMID)", in the keychain
          APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   also notarize and staple the app
  Windows WINDOWS_SIGN_PFX + WINDOWS_SIGN_PASSWORD      a .pfx certificate file, or
          WINDOWS_SIGN_THUMBPRINT                       a certificate in the Windows certificate
                                                        store (also cloud/USB token certificates)
          WINDOWS_SIGN_TIMESTAMP (default http://timestamp.digicert.com)

docs/admin.md («Тоон гарын үсэг») explains how to get the certificates.
"""

import argparse
import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*command, secret=None):
    shown = ['***' if secret and part == secret else part for part in command]
    print('$', ' '.join(shown), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def sign_macos(app, archive):
    """Developer ID signature, then notarization when Apple credentials are given; else ad-hoc."""
    identity = os.environ.get('MACOS_SIGN_IDENTITY')
    if not identity:
        # An ad-hoc signature is required for the app to start on Apple Silicon; it is not a
        # Developer ID signature, so Gatekeeper still warns on first start.
        run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', app)
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        return False
    entitlements = str(ROOT / 'packaging' / 'entitlements.plist')
    run(
        '/usr/bin/codesign', '--force', '--deep', '--options', 'runtime', '--timestamp',
        '--entitlements', entitlements, '--sign', identity, app,
    )  # fmt: skip
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2', app)
    apple_id, team, password = (os.environ.get(name) for name in ('APPLE_ID', 'APPLE_TEAM_ID', 'APPLE_APP_PASSWORD'))
    if apple_id and team and password:
        run('/usr/bin/ditto', '-c', '-k', '--keepParent', app, str(archive))
        run(
            '/usr/bin/xcrun', 'notarytool', 'submit', str(archive), '--apple-id', apple_id, '--team-id', team,
            '--password', password, '--wait', secret=password,
        )  # fmt: skip
        run('/usr/bin/xcrun', 'stapler', 'staple', app)
        archive.unlink()
        run('/usr/sbin/spctl', '--assess', '--type', 'execute', '--verbose=2', app)
    return True


def signtool():
    found = shutil.which('signtool')
    if found:
        return found
    kits = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)') + r'\Windows Kits\10\bin'
    candidates = sorted(glob.glob(kits + r'\10.*\x64\signtool.exe'))
    if not candidates:
        raise SystemExit('signtool.exe was not found; install the Windows SDK.')
    return candidates[-1]


def sign_windows(executable):
    pfx, thumbprint = os.environ.get('WINDOWS_SIGN_PFX'), os.environ.get('WINDOWS_SIGN_THUMBPRINT')
    if not pfx and not thumbprint:
        return False
    tool = signtool()
    timestamp = os.environ.get('WINDOWS_SIGN_TIMESTAMP', 'http://timestamp.digicert.com')
    password = os.environ.get('WINDOWS_SIGN_PASSWORD', '')
    which = ['/f', pfx, '/p', password] if pfx else ['/sha1', thumbprint]
    run(tool, 'sign', '/fd', 'sha256', '/tr', timestamp, '/td', 'sha256', *which, str(executable), secret=password)
    run(tool, 'verify', '/pa', '/v', str(executable))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'packaging' / 'out', help='Output folder')
    parser.add_argument(
        '--sign-only', action='store_true', help='Sign and zip an app built before (CI keeps secrets out of the build)'
    )
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.sign_only:
        build(out)
    finish(out)


def build(out):
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


def finish(out):
    if sys.platform == 'darwin':
        app = str(out / 'WorkTrack.app')
        # Extended attributes (e.g. from a Desktop folder) block signing.
        run('/usr/bin/xattr', '-crs', app)  # -s: also the framework symlinks themselves
        archive = out / 'WorkTrack-macos.zip'
        archive.unlink(missing_ok=True)
        signed = sign_macos(app, archive)
        # ditto keeps the app bundle's symlinks and permissions intact.
        run('/usr/bin/ditto', '-c', '-k', '--keepParent', app, str(archive))
    else:
        signed = sys.platform == 'win32' and sign_windows(out / 'WorkTrack' / 'WorkTrack.exe')
        name = 'windows' if sys.platform == 'win32' else 'linux'
        archive = Path(shutil.make_archive(str(out / f'WorkTrack-{name}'), 'zip', out, 'WorkTrack'))
    note = 'signed' if signed else 'not signed with a certificate: first start shows a warning'
    print(f'Built {archive} ({archive.stat().st_size // 1_000_000} MB, {note})', flush=True)


if __name__ == '__main__':
    main()
