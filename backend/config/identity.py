"""Non-secret source identity captured when Django settings load."""
import hashlib
import os
from pathlib import Path


def source_digest(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parent.parent
    digest=hashlib.sha256()
    files=[]
    for folder,directories,names in os.walk(root):
        directories[:]=[name for name in directories if name not in {'__pycache__','.venv','venv','backups','staticfiles','.git'}]
        files.extend(Path(folder)/name for name in names if name.endswith('.py'))
    files.sort()
    requirements=root/'requirements.txt'
    if requirements.exists(): files.append(requirements)
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()


def workspace_id(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parent.parent
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()
