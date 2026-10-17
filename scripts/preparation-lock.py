"""Crash-released OS locks for generated offline preparation outputs."""
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def exclusive_worker(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with (output/'.worker.lock').open('a+b') as lock:
        if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise RuntimeError('Another preparation worker already owns this output') from error
        else:
            import fcntl
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:raise RuntimeError('Another preparation worker already owns this output') from error
        try:yield
        finally:
            lock.seek(0)
            if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock,fcntl.LOCK_UN)
