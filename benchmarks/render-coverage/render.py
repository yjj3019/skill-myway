"""Render the fixed HTML example with a local Chromium executable and a fresh profile."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def record(path):
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    fixture = Path(__file__).resolve().parent
    plan = json.loads((fixture / "plan.json").read_text(encoding="utf-8"))["artifacts"]["weekly-review"]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "sample.html"
    shutil.copyfile(fixture / source.name, source)
    source_record = record(source)
    if source_record["sha256"] != plan["source_sha256"]:
        raise ValueError("fixture differs from the pre-render plan")
    surfaces = []
    with tempfile.TemporaryDirectory(dir=out) as profile:
        for index, (name, (width, height)) in enumerate(plan["surfaces"].items(), 1):
            image = out / name
            subprocess.run([str(args.browser.resolve()), "--headless", "--disable-gpu",
                            "--no-first-run", "--disable-background-networking",
                            "--force-device-scale-factor=1", f"--user-data-dir={profile}",
                            f"--window-size={width},{height}", f"--screenshot={image}",
                            source.as_uri()], check=True, timeout=60)
            with Image.open(image, formats=("PNG",)) as pixels:
                observed = pixels.width
            render = record(image)
            surfaces.append({"index": index, "render": render,
                             "measurements": [{"name": "capture width", "value": observed,
                                               "unit": "px", "location": "entire PNG"}],
                             "review": {"source_sha256": source_record["sha256"],
                                        "render_sha256": render["sha256"], "status": "NOT VERIFIED",
                                        "open_critical": 0, "open_major": 0}})
    manifest = {"schema_version": 3, "artifacts": [{"id": "weekly-review", "kind": "html",
                 "source": source_record, "surfaces": surfaces}]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
