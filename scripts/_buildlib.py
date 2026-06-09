"""
Shared constants and helpers for the Blender add-on build scripts.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ADDONS = {"scenery": "scenery_renderer_addon"}

RENDERER_DIST = "openrct2-x7-renderer"
RENDERER_PREFIX = "openrct2_x7_renderer"
RENDERER_VERSION = "0.3.1"

OBJECTCOMMON_DIST = "OpenRCT2-ObjectCommon"
OBJECTCOMMON_PREFIX = "openrct2_objectcommon"
OBJECTCOMMON_VERSION = "0.1.3"

FRONTEND_PREFIX = "openrct2_scenerygenerator"

DEPS = ("numpy", "pillow", "pyyaml")


def run(cmd: list[str], *, capture: bool = False) -> str:
    """Run a command, echoing it; raise on failure. Return stdout if captured."""
    print("+", " ".join(cmd))
    res = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return res.stdout if capture else ""


def renderer_spec() -> str:
    """The pinned dist==version requirement for the bundled renderer."""
    return f"{RENDERER_DIST}=={RENDERER_VERSION}"


def objectcommon_spec() -> str:
    """The pinned dist==version requirement for the bundled shared layer."""
    return f"{OBJECTCOMMON_DIST}=={OBJECTCOMMON_VERSION}"


def pip_download_cmd(
    pip_prefix: list[str],
    *,
    dest: Path,
    py_version: str,
    abi: str,
    platform_tags: list[str],
    specs: list[str],
) -> list[str]:
    cmd = [
        *pip_prefix,
        "download",
        "--only-binary=:all:",
        "--no-deps",
        "--python-version",
        py_version,
        "--implementation",
        "cp",
        "--abi",
        abi,
        "-d",
        str(dest),
    ]
    for tag in platform_tags:
        cmd += ["--platform", tag]
    return cmd + specs


def one_renderer_wheel(d: Path) -> Path:
    wheels = list(d.glob(f"{RENDERER_PREFIX}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one renderer wheel in {d}, found {wheels}")
    return wheels[0]


def wheels_block(names: list[str]) -> str:
    entries = sorted(set(names))
    return "\n".join(["wheels = ["] + [f'    "./wheels/{n}",' for n in entries] + ["]"])


def set_toml_array(text: str, key: str, block: str) -> str:
    new_text, n = re.subn(rf"{key} = \[.*?]" , block, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit(f"Could not find a '{key} = [...]' block in the manifest")
    return new_text
