"""Print reviewable SHA-256 pins for the repository's UTF-8 evaluation corpus."""
import hashlib
import json
import stat
from pathlib import Path


def inventory(directory):
    entries = {}

    def visit(path):
        info = path.lstat()
        if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"linked evaluation input: {path.name}")
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(info.st_mode) and path.suffix in {".md", ".json"}:
            # Universal newlines keep the text baseline portable across Git checkouts.
            content = path.read_text(encoding="utf-8").encode("utf-8")
            entries[path.relative_to(directory).as_posix()] = hashlib.sha256(content).hexdigest()
        else:
            raise ValueError(f"unexpected evaluation input: {path.name}")

    visit(directory)
    if not entries:
        raise ValueError("empty evaluation corpus")
    return entries


if __name__ == "__main__":
    corpus = Path(__file__).resolve().parents[1] / "tests" / "eval_cases"
    print(json.dumps(inventory(corpus), sort_keys=True, indent=2))
