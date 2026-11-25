"""Explicitly created presentation workspaces; never adopt arbitrary databases."""
from contextlib import contextmanager, closing
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3


class WorkspaceError(ValueError):
    pass


def fingerprint(snapshot, av_report):
    return sha256(json.dumps([snapshot, av_report], sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _regular(path):
    return path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1


@dataclass(frozen=True)
class Workspace:
    path: Path
    resume: bool
    digest: str

    def verify(self):
        if not _regular(self.path):
            raise WorkspaceError('DEMO_WORKSPACE_DATABASE_INVALID')
        try:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as db:
                row = db.execute('SELECT schema_version, input_sha256 FROM demo_workspace_identity').fetchall()
                if row != [(1, self.digest)]:
                    raise WorkspaceError('DEMO_WORKSPACE_INPUT_MISMATCH')
        except sqlite3.Error as exc:
            raise WorkspaceError('DEMO_WORKSPACE_DATABASE_INVALID') from exc

    def seal(self):
        if self.resume or not _regular(self.path):
            raise WorkspaceError('DEMO_WORKSPACE_DATABASE_INVALID')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True)) as db, db:
            db.execute('CREATE TABLE demo_workspace_identity (schema_version INTEGER NOT NULL, input_sha256 TEXT NOT NULL)')
            db.execute('INSERT INTO demo_workspace_identity VALUES (1, ?)', (self.digest,))


@contextmanager
def open_workspace(directory, snapshot, av_report):
    """Lock the workspace for the process lifetime, even across HTTP requests.

    An existing directory must contain both the lock file and a sealed demo DB.
    OS file locks are released on process death; no stale PID heuristics.
    """
    directory = Path(directory).absolute()
    if directory.is_symlink():
        raise WorkspaceError('DEMO_WORKSPACE_DIRECTORY_INVALID')
    try:
        directory.mkdir(mode=0o700)
        fresh = True
    except FileExistsError:
        fresh = False
    if not directory.is_dir() or directory.is_symlink():
        raise WorkspaceError('DEMO_WORKSPACE_DIRECTORY_INVALID')
    lock_path = directory / 'presentation.lock'
    db_path = directory / 'demo.sqlite'
    if not fresh and (not _regular(lock_path) or not _regular(db_path)):
        raise WorkspaceError('DEMO_WORKSPACE_NOT_INITIALIZED')
    with lock_path.open('x+b' if fresh else 'r+b') as lock:
        if fresh:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise WorkspaceError('DEMO_WORKSPACE_BUSY') from exc
        try:
            work = Workspace(db_path, not fresh, fingerprint(snapshot, av_report))
            if work.resume:
                work.verify()
            yield work
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
