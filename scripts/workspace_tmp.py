"""Create temporary work only inside this repository's workspace."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def temp_root():
    root = ROOT.resolve(strict=True)
    candidate = root / ".myway-tmp"
    if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
        raise ValueError("workspace temporary root must not be a link")
    candidate.mkdir(exist_ok=True)
    if not candidate.resolve(strict=True).is_relative_to(root):
        raise ValueError("workspace temporary root escaped the repository")
    return candidate
