#!/usr/bin/env python3
"""Compile and exercise native startup/Quit in a disposable workspace, without monitoring."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parent


def main():
    if sys.platform!='darwin':
        raise SystemExit('Native macOS verification requires macOS and Command Line Tools.')
    from desktop import build_macos_app
    with tempfile.TemporaryDirectory(prefix='worktrack-native-qa-',dir='/private/tmp') as directory:
        root=Path(directory);(root/'desktop').mkdir();(root/'.runtime').mkdir()
        (root/'.venv').symlink_to(Path(sys.prefix),target_is_directory=True)
        for name in ('WorkTrack.m','app_control.py'):
            shutil.copyfile(ROOT/'desktop'/name,root/'desktop'/name)
        (root/'worktrack.py').write_text('''import argparse,fcntl,json,os,signal,threading
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--desktop',action='store_true');p.add_argument('--app-id');a=p.parse_args()
stop=threading.Event();signal.signal(signal.SIGTERM,lambda *_:stop.set())
with Path('.runtime/launcher.lock').open('a+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 Path('.runtime/probe.json').write_text(json.dumps({'pid':os.getpid(),'instance':a.app_id}))
 stop.wait(60)
''')
        previous=build_macos_app.ROOT
        try:
            build_macos_app.ROOT=root;build_macos_app.build()
        finally:build_macos_app.ROOT=previous
        bundle=root/'WorkTrack.app';info=bundle/'Contents/Info.plist'
        values=plistlib.loads(info.read_bytes());identifier='mn.worktrack.qa.'+uuid.uuid4().hex
        values['CFBundleIdentifier']=identifier;info.write_bytes(plistlib.dumps(values))
        subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(bundle)],check=True)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(bundle)],check=True)
        try:
            subprocess.run(['/usr/bin/open','-n',str(bundle)],check=True)
            deadline=time.monotonic()+20
            while not (root/'.runtime/probe.json').exists():
                if time.monotonic()>deadline:raise RuntimeError('Native app did not launch its helper.')
                time.sleep(.1)
            probe=json.loads((root/'.runtime/probe.json').read_text())
            recorded=json.loads((root/'.runtime/macos-app.json').read_text())
            if probe!=recorded:raise RuntimeError('Native helper ownership does not match the launched process.')
            print('PASS: native icon launched the owned synthetic runner; no OS observations or camera.',flush=True)
            script=f'with timeout of 10 seconds\ntell application id "{identifier}" to quit\nend timeout'
            subprocess.run(['/usr/bin/osascript','-e',script],timeout=12,check=True)
            deadline=time.monotonic()+10
            while True:
                try:os.kill(probe['pid'],0)
                except ProcessLookupError:break
                if time.monotonic()>deadline:raise RuntimeError('Native Quit did not stop its owned runner.')
                time.sleep(.1)
            print('PASS: native Quit stopped exactly its owned runner.',flush=True)
        finally:
            state=root/'.runtime/macos-app.json'
            if state.exists():
                value=json.loads(state.read_text())
                subprocess.run([sys.executable,str(root/'desktop/app_control.py'),'stop',value['instance']],check=False)
            for line in subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True).splitlines():
                pid,_,command=line.strip().partition(' ')
                if (command==str(bundle/'Contents/MacOS/WorkTrack') or
                    str(root/'desktop/app_control.py')+' start ' in command or
                    str(root/'worktrack.py')+' --desktop' in command):
                    try:os.kill(int(pid),signal.SIGTERM)
                    except ProcessLookupError:pass
    print('PASS: disposable native workspace removed; live services and data untouched.',flush=True)


if __name__=='__main__':main()
