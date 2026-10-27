"""Local paths only. No UNC shares, URLs, or Windows mapped network drives."""
import os
from pathlib import Path


def local_path(value):
    raw = os.fspath(value)
    if not isinstance(raw, str) or raw.startswith(('\\\\', '//')) or '://' in raw or '\x00' in raw:
        raise ValueError('LOCAL_PATH_REQUIRED')
    path = Path(raw).expanduser()
    if os.name == 'nt':
        import ctypes
        anchor = path.absolute().anchor
        if ctypes.windll.kernel32.GetDriveTypeW(anchor) == 4:
            raise ValueError('NETWORK_DRIVE_BLOCKED')
    return path
