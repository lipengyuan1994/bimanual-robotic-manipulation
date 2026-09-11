"""POSIX worker exclusion retained by every live owner of a duplicated descriptor."""

from __future__ import annotations

import errno
import os
import stat
from multiprocessing.reduction import DupFd
from pathlib import Path


def _spawn_reference(duplicate):
    return duplicate


class _LeaseTransfer:
    def __init__(self, owner):
        self.owner = owner

    def __reduce__(self):
        # Duplicate during spawn serialization, using the spawn descriptor channel.
        # Pre-duplicating would rely on a resource-sharing server in the dying owner.
        if self.owner._descriptor is None:
            raise RuntimeError("Worker lease closed before spawn")
        return _spawn_reference, (DupFd(self.owner._descriptor),)


class WorkerLease:
    """Keep the lock file in place; descriptor lifetime is the authority, never a PID.

    A guardian must retain its descriptor until its worker has exited. A spawned
    worker detaches an exported descriptor before model initialization and retains
    it until exit. Closing one duplicate must not unlock the remaining owners.
    This primitive is not yet a substitute for guardian integration.
    """

    def __init__(self, descriptor: int):
        self._descriptor: int | None = descriptor

    @classmethod
    def acquire(cls, path: Path) -> WorkerLease:
        if os.name != "posix":
            raise RuntimeError("Worker leases require a supported POSIX host")
        import fcntl

        path = Path(path)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Worker lease must be a regular file")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN):
                    raise RuntimeError("A workflow worker still holds this lease") from error
                raise
            return cls(descriptor)
        except BaseException:
            os.close(descriptor)
            raise

    @classmethod
    def from_spawn(cls, exported) -> WorkerLease:
        return cls(exported.detach())

    def export_for_spawn(self):
        if self._descriptor is None:
            raise RuntimeError("Worker lease is closed")
        return _LeaseTransfer(self)

    def close(self):
        if self._descriptor is not None:
            descriptor, self._descriptor = self._descriptor, None
            # LOCK_UN would unlock a worker's duplicate too; close only this owner.
            os.close(descriptor)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
