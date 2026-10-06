"""Walk a directory tree without following Windows junctions or symlinks."""

from __future__ import annotations

import os
import stat

# Directories never worth scanning; pruned before descending.
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "artifacts"})


def _is_junction(path: str) -> bool:
    """A Windows junction or a symlink. os.walk follows junctions, so we prune them."""
    if os.path.islink(path):
        return True
    try:
        attrs = os.lstat(path).st_file_attributes  # Windows only
    except (AttributeError, OSError):
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def walk_files(root: str):
    """Yield file paths under root, pruning build dirs and never following a junction.

    os.walk descends into Windows junctions, so reparse-point directories are pruned in
    place and junction files skipped; a junction hub would otherwise reflect every repo back.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIRS and not _is_junction(os.path.join(dirpath, d))
        ]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if not _is_junction(fpath):
                yield fpath
