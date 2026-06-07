"""Shared constants and helpers for the Blender add-on build scripts.

Used by both ``collect_wheels.py`` (CI: bundle every-platform wheels) and
``build_plugin_local.py`` (dev: build a single-platform zip). Keeping the
renderer pin, dependency list, and manifest rewriting in one place stops the two
scripts from drifting; previously each carried its own copy of
``RENDERER_VERSION``, the ``pip download`` invocation, and the manifest regex.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Add-on label -> source directory (room for more add-ons later).
ADDONS = {"scenery": "scenery_renderer_addon"}

# External renderer: PyPI dist name, wheel-filename prefix, and the exact version
# to bundle. Keep RENDERER_VERSION in step with the floor in pyproject.toml's
# `openrct2-x7-renderer>=...` dependency.
RENDERER_DIST = "openrct2-x7-renderer"
RENDERER_PREFIX = "openrct2_x7_renderer"
RENDERER_VERSION = "0.3.1"

# Shared layer (openrct2_object_common): PyPI dist name, wheel-filename prefix,
# and the exact version to bundle. Pure Python (py3-none-any), so one wheel
# covers every target. Downloaded from PyPI alongside the renderer. Keep
# OBJECTCOMMON_VERSION in step with the floor in pyproject.toml's
# `OpenRCT2-ObjectCommon>=...` dependency.
OBJECTCOMMON_DIST = "OpenRCT2-ObjectCommon"
OBJECTCOMMON_PREFIX = "openrct2_objectcommon"
OBJECTCOMMON_VERSION = "0.1.2"

# This repo's pure-Python front-end wheel (built + placed by the caller).
FRONTEND_PREFIX = "openrct2_scenerygenerator"

# Runtime deps that must be vendored into the add-on alongside the renderer.
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
    """The pinned ``dist==version`` requirement for the bundled renderer."""
    return f"{RENDERER_DIST}=={RENDERER_VERSION}"


def objectcommon_spec() -> str:
    """The pinned ``dist==version`` requirement for the bundled shared layer."""
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
    """Build a ``pip download`` command for one (Python, platform) target.

    ``pip_prefix`` is the interpreter+pip invocation to prepend, e.g.
    ``[sys.executable, "-m", "pip"]`` (collect_wheels, already inside the uv env)
    or ``["uv", "run", "--with", "pip", "python", "-m", "pip"]``
    (build_plugin_local). Several ``platform_tags`` let pip pick each package's
    compatible wheel (numpy and Pillow publish different OS minimums).
    """
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
    """The single renderer wheel in ``d`` (raises if not exactly one)."""
    wheels = list(d.glob(f"{RENDERER_PREFIX}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one renderer wheel in {d}, found {wheels}")
    return wheels[0]


def wheels_block(names: list[str]) -> str:
    """The manifest ``wheels = [...]`` block listing each wheel filename."""
    entries = sorted(set(names))
    return "\n".join(["wheels = ["] + [f'    "./wheels/{n}",' for n in entries] + ["]"])


def set_toml_array(text: str, key: str, block: str) -> str:
    """Replace the ``{key} = [...]`` array in ``text`` with ``block``.

    Raises ``SystemExit`` if the array isn't found exactly once.
    """
    new_text, n = re.subn(rf"{key} = \[.*?\]", block, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit(f"Could not find a '{key} = [...]' block in the manifest")
    return new_text
