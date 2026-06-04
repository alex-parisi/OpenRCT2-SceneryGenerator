"""Rewrite the project version in pyproject.toml and the Blender manifest.

Invoked from CI before wheels are built and before the manifest is regenerated,
so the wheels carry the release version and ``collect_wheels.py`` (which sources
the version from pyproject.toml) lists them under the right filenames.

Usage:
    python scripts/ci/set_version.py <version>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "pyproject.toml",
    ROOT / "scenery_addon" / "blender_manifest.toml",
]
# Match the first top-level `version = "..."` assignment in each file.
PATTERN = re.compile(r'^version\s*=\s*"[^"]*"', re.MULTILINE)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: set_version.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1]
    for path in TARGETS:
        text = path.read_text()
        new_text, n = PATTERN.subn(f'version = "{version}"', text, count=1)
        if n != 1:
            raise SystemExit(f"no version line found in {path}")
        path.write_text(new_text)
        print(f"{path.relative_to(ROOT)}: version -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
