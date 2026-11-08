"""Shared ownership for the patched pipeline and Fast Review queue."""
import json, os, socket, uuid
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

@contextmanager
def run_lock(root, action):
    path=Path(root)/'.bat_daily_tool.lock'
    token=uuid.uuid4().hex
    try:
        handle=path.open('x',encoding='utf8')
    except FileExistsError:
        raise RuntimeError(f'Bat tools already locked: {path}. No changes made by this process. Check the running task before using stale-lock recovery.')
    try:
        with handle:
            json.dump(dict(token=token,pid=os.getpid(),host=socket.gethostname(),action=action,
                           started_utc=datetime.now(timezone.utc).isoformat()),handle)
        yield
    finally:
        try:
            if json.loads(path.read_text()).get('token')==token:path.unlink()
        except (OSError,ValueError,AttributeError):
            pass
