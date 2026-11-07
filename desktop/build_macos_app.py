#!/usr/bin/env python3
"""Build an ad-hoc signed local macOS launcher; no Developer ID/notarization."""
from pathlib import Path
import plistlib
import subprocess
import sys
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def build():
    if sys.platform!='darwin': raise SystemExit('WorkTrack.app is built on macOS only.')
    target=ROOT/'WorkTrack.app'
    with tempfile.TemporaryDirectory(prefix='worktrack-build-',dir='/private/tmp') as directory:
        staged=Path(directory)/'WorkTrack.app'
        (staged/'Contents/MacOS').mkdir(parents=True)
        subprocess.run(['/usr/bin/clang','-fobjc-arc','-framework','Cocoa','-mmacosx-version-min=12.0',
            str(ROOT/'desktop/WorkTrack.m'),'-o',str(staged/'Contents/MacOS/WorkTrack')],check=True)
        path=staged/'Contents/Info.plist'
        value=dict(CFBundleName='WorkTrack',CFBundleDisplayName='WorkTrack',CFBundleIdentifier='mn.worktrack.local',
            CFBundleExecutable='WorkTrack',CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0',
            WorkTrackProjectRoot=str(ROOT),
            NSCameraUsageDescription='WorkTrack camera stores presence and confidence only, after you enable it.',
            LSMinimumSystemVersion='12.0')
        path.write_bytes(plistlib.dumps(value))
        # Sign away from Desktop/iCloud, which may attach Finder metadata concurrently.
        subprocess.run(['/usr/bin/xattr','-cr',str(staged)],check=True)
        subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(staged)],check=True)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(staged)],check=True)
        if target.is_symlink(): target.unlink()
        elif target.exists(): shutil.rmtree(target)
        shutil.copytree(staged,target)
    print(target)


if __name__=='__main__':build()
