# PyInstaller recipe for the team-computer app: web page (prebuilt dist/), agent and reminders.
# No Django, database or camera: those stay on the organisation's server / source checkout.
# Build with:  python packaging/build_client.py
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent

analysis = Analysis(
    [str(root / 'worktrack.py')],
    pathex=[str(root)],
    datas=[
        (str(root / 'dist'), 'dist'),
        (str(root / 'agent' / 'config.example.json'), 'agent'),
        *collect_data_files('tzdata'),  # Windows has no system time zone database.
    ],
    hiddenimports=[
        'agent.main',
        'desktop.service',
        'desktop.gateway',
        'desktop.usage',
        'desktop.usage_sync',
        'desktop.reminders',
        'desktop.autostart',
        'desktop.updates',
        'desktop.tls',
        'agent.transport',
        'agent.version',
        'tzdata',
    ],
    # Server and camera code is reachable only from modes this app never runs. cryptography only
    # makes the office server's certificate; a team computer checks it with the standard library.
    excludes=[
        'backend',
        'django',
        'rest_framework',
        'src',
        'cv2',
        'torch',
        'ultralytics',
        'numpy',
        'tkinter',
        'cryptography',
    ],
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name='WorkTrack',
    # Windows keeps a console window: Ctrl+C works and the agent can be stopped gently.
    console=sys.platform == 'win32',
)
folder = COLLECT(executable, analysis.binaries, analysis.datas, name='WorkTrack')
if sys.platform == 'darwin':
    app = BUNDLE(
        folder,
        name='WorkTrack.app',
        bundle_identifier='mn.worktrack.client',
        info_plist={
            'CFBundleName': 'WorkTrack',
            'CFBundleShortVersionString': '1.0.0',
            'LSUIElement': True,  # No Dock icon: the browser page is the window; quit from it.
            'NSAppleEventsUsageDescription': 'WorkTrack идэвхтэй аппын нэрийг (цонхны гарчиг биш) уншина.',
        },
    )
