"""Stage a binary file beside its destination and publish it without overwriting."""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def new_output(path):
    path = Path(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as stream:
            temp_path = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            os.rename(temp_path, path)
        else:
            os.link(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
