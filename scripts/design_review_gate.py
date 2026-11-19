#!/usr/bin/env python3
"""Repository entry point for the packaged visual-design evidence checker."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/myway/skills/visual-design/scripts"))
from check_design_review import check, main


if __name__ == "__main__":
    sys.exit(main())
