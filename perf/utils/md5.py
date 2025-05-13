"""
This module contains code to calculate an HASH for all Cython files.

In this context, it is used to verify if recompiling Cython modules is necessary across
commits, when running benchmarks across commits (historyrun.py).
"""

import glob
import hashlib
from pathlib import Path

from _hashlib import HASH


def iter_cython_files():
    return (item for item in glob.glob("./**/*.py*") if item[-4:] in {".pyx", ".pxd"})


def md5_cython_files() -> str:
    """
    Creates an HASH of all .pyx and .pxd files under the current working directory,
    to detect changes across commits and know if a re-compilation is needed.
    """
    _hash = hashlib.md5()
    for file in iter_cython_files():
        hash.update(file.encode())
        md5_update_from_file(file, _hash)
    return _hash.hexdigest()


def md5_update_from_file(filename: str | Path, hash: HASH) -> HASH:
    with open(str(filename), "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash.update(chunk)
    return hash
