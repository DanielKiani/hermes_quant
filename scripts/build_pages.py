"""Build the static GitHub Pages artifact with project-relative asset paths."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "_site"
FRONTEND_FILES = ("index.html", "styles.css", "app.js", "demo-data.js", "favicon.svg")


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    for name in FRONTEND_FILES:
        shutil.copy2(FRONTEND / name, OUTPUT / name)
    shutil.copytree(FRONTEND / "demo", OUTPUT / "demo")
    shutil.copytree(ASSETS, OUTPUT / "media", ignore=shutil.ignore_patterns("hermes_banner.png"))
    (OUTPUT / ".nojekyll").touch()
    shutil.copy2(OUTPUT / "index.html", OUTPUT / "404.html")
    print(f"Built GitHub Pages artifact at {OUTPUT}")


if __name__ == "__main__":
    main()
