"""Module for writing files so that readers never see half a file."""

import os
import tempfile
from pathlib import Path


def write_file(path: Path, text: str, mode: int = 0o644) -> None:
    """Replace a file in one step.

    The text goes to a temporary file in the same folder first, then that file
    replaces the target. If two runs write at the same time, the file holds
    one of the two versions, never a mix. The target always gets ``mode``.

    :param path: File to write. If it is a symlink, the file it points to is
        replaced.
    :param text: Full new content of the file.
    :param mode: Permissions of the new file.
    """
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except BaseException:
        os.unlink(temp_name)
        raise
