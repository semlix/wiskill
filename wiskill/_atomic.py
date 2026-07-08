"""Atomic text-file writes: write to a sibling temp file, then rename over
the target. os.replace is atomic on POSIX and Windows, so a crash or kill
mid-write never leaves a truncated/partial file at `path`."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise
