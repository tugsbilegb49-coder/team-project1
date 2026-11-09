"""Build only our camera host; never patch the installed Python application."""

import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile


def build(root):
    root = Path(root).resolve()
    if sys.platform != 'darwin':
        return None
    source = root / 'desktop/CameraHost.m'
    identity = {
        'source': hashlib.sha256(source.read_bytes()).hexdigest(),
        'builder': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': sys.executable,
        'base': sys.base_prefix,
        'version': sys.version,
        'root': str(root),
    }
    cache = Path(tempfile.gettempdir()).resolve() / (
        'worktrack-camera-' + hashlib.sha256(str(root).encode()).hexdigest()[:16]
    )
    cache.mkdir(mode=0o700, exist_ok=True)
    if cache.is_symlink() or cache.stat().st_uid != os.getuid() or cache.stat().st_mode & 0o077:
        raise RuntimeError('Camera build cache нь зөвхөн өөрийн private хавтас байх ёстой.')
    sessions = cache / 'sessions'
    sessions.mkdir(mode=0o700, exist_ok=True)
    bundle = cache / 'WorkTrack Camera.app'
    identity['bundle'] = str(bundle)
    executable = bundle / 'Contents/MacOS/WorkTrackCamera'
    stamp = root / '.runtime/camera-host-build.json'
    try:
        if executable.is_file() and json.loads(stamp.read_text()) == identity:
            return executable
    except (OSError, ValueError):
        pass
    root.joinpath('.runtime').mkdir(exist_ok=True)
    library = Path(sys.base_prefix) / 'Python'
    if not library.is_file():
        library = Path(sysconfig.get_config_var('LIBDIR')) / sysconfig.get_config_var('LDLIBRARY')
    if not library.is_file():
        raise RuntimeError('Camera host-д shared Python library хэрэгтэй. Python.org framework build ашиглана уу.')
    with tempfile.TemporaryDirectory(prefix='worktrack-camera-build-', dir='/private/tmp') as directory:
        staged = Path(directory) / bundle.name
        (staged / 'Contents/MacOS').mkdir(parents=True)
        metadata = {
            'CFBundleName': 'WorkTrack Camera',
            'CFBundleDisplayName': 'WorkTrack Camera',
            'CFBundleIdentifier': 'mn.worktrack.camera',
            'CFBundleExecutable': 'WorkTrackCamera',
            'CFBundlePackageType': 'APPL',
            'CFBundleVersion': '1',
            'LSUIElement': True,
            'NSDesktopFolderUsageDescription': 'WorkTrack reads its project configuration and writes presence metadata in its own project folder.',
            'NSCameraUsageDescription': 'WorkTrack detects whether a person is present. Frames stay in memory; no photos or video are saved.',
            'WorkTrackProjectRoot': str(root),
            'WorkTrackPython': str(root / '.venv/bin/python'),
            'WorkTrackSessionDirectory': str(sessions),
        }
        (staged / 'Contents/Info.plist').write_bytes(plistlib.dumps(metadata))
        subprocess.run(
            [
                '/usr/bin/clang',
                '-fobjc-arc',
                '-framework',
                'Cocoa',
                '-framework',
                'AVFoundation',
                '-I' + sysconfig.get_config_var('INCLUDEPY'),
                str(source),
                str(library),
                '-o',
                str(staged / 'Contents/MacOS/WorkTrackCamera'),
            ],
            check=True,
        )
        entitlements = Path(directory) / 'entitlements.plist'
        entitlements.write_bytes(plistlib.dumps({'com.apple.security.device.camera': True}))
        subprocess.run(
            ['/usr/bin/codesign', '--force', '--sign', '-', '--entitlements', str(entitlements), str(staged)],
            check=True,
        )
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(staged)], check=True)
        if bundle.exists():
            shutil.rmtree(bundle)
        shutil.copytree(staged, bundle)
    from agent.token_store import atomic_json_write

    atomic_json_write(stamp, identity)
    return executable


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parents[1]))
