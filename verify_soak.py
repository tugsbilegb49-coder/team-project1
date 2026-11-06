#!/usr/bin/env python3
"""Real-time synthetic multi-device HTTP soak in an isolated SQLite test database."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--devices',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.seconds<=86400 or not 1<=args.devices<=50:
        parser.error('Use 1–86400 seconds and 1–50 synthetic devices.')
    root=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='worktrack-soak-') as directory:
        temp=Path(directory)
        (temp/'soak_settings.py').write_text('from config.settings import *\nDATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":'+repr(str(temp/'soak.sqlite3'))+'}}\n')
        env=os.environ.copy()
        env.update({'DJANGO_SETTINGS_MODULE':'soak_settings','PYTHONPATH':str(temp)+os.pathsep+str(root/'backend'),
                    'WORKTRACK_SOAK_SECONDS':str(args.seconds),'WORKTRACK_SOAK_DEVICES':str(args.devices)})
        return subprocess.run([sys.executable,'manage.py','test','activity.test_soak','--noinput'],cwd=root,env=env).returncode


if __name__=='__main__':
    raise SystemExit(main())
