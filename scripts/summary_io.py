"""Publish a complete evaluation summary without replacing another run's output."""
import json
from pathlib import Path

from atomic_output import new_output


def save_summary(path, summary):
    path = Path(path)
    data = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _publish(path, data)
    except FileExistsError:
        raise
    except OSError:
        # Retry the same serialized result once, without repeating model calls.
        _publish(path, data)


def _publish(path, data):
    with new_output(path) as stream:
        stream.write(data)
