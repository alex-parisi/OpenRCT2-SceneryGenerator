#!/usr/bin/env python3
"""Bundle the Blender add-on's wheels and regenerate the manifest.

Blender extensions run in an isolated Python env and install ONLY the wheels
listed in ``blender_manifest.toml``; pip is never consulted at install time.
So everything the add-on imports must be vendored as a wheel for each platform x
Python combination Blender ships, or it fails to import (e.g. "No module named
'PIL'").

The add-on bundles three kinds of wheel:

  1. The renderer (``openrct2-x7-renderer``): the external PyPI package with
     the Embree-vendored native extension. Platform + Python specific; downloaded
     here straight from PyPI (no CI build needed).
  2. The dependency wheels (numpy, Pillow, PyYAML). Platform + Python
     specific; downloaded from PyPI.
  3. The front-end wheel (``openrct2_scenerygenerator``): this repo, now
     pure-Python (``py3-none-any``, one wheel for every target). Built separately
     with ``uv build --wheel`` and placed in ``scenery_renderer_addon/wheels/`` before this
     runs.

This script downloads (1) and (2) for all targets, then rewrites the manifest's
``wheels = [...]`` to list every wheel present in ``scenery_renderer_addon/wheels/``
(including the pre-placed front-end wheel).

Run from the repo root (pip must be importable):

    uv run --with pip python scripts/collect_wheels.py
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADDON = REPO / "scenery_renderer_addon"
WHEELS = ADDON / "wheels"
MANIFEST = ADDON / "blender_manifest.toml"

# External renderer: PyPI dist name, wheel-filename prefix, and the pinned
# version to bundle. Keep RENDERER_VERSION in step with the floor in
# pyproject.toml's `openrct2-x7-renderer>=...` dependency.
RENDERER_DIST = "openrct2-x7-renderer"
RENDERER_PREFIX = "openrct2_x7_renderer"
RENDERER_VERSION = "0.2.0"

# This repo's pure-Python front-end wheel (built + placed by the caller).
FRONTEND_PREFIX = "openrct2_scenerygenerator"

DEPS = ("numpy", "pillow", "pyyaml")

# (python version, abi tag) for each interpreter Blender ships: 3.11 (4.2/4.5
# LTS), 3.13 (5.x).
PYTHONS = (("3.11", "cp311"), ("3.13", "cp313"))

# (label, --platform tags). Several dep tags per OS let pip pick each package's
# compatible wheel; e.g. numpy publishes a higher macOS minimum than Pillow.
TARGETS = (
    ("win_amd64", ["win_amd64"]),
    (
        "macosx_11_0_arm64",
        ["macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_13_0_arm64", "macosx_14_0_arm64"],
    ),
    (
        "manylinux_2_28_x86_64",
        ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"],
    ),
)


def ensure_pip() -> None:
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit(
            "pip is not available in this interpreter. Re-run with:\n"
            "  uv run --with pip python scripts/collect_wheels.py"
        ) from None


def download_specs() -> list[str]:
    # Renderer pinned to the bundled release; deps pinned to the versions
    # resolved in this env so they match what the renderer was built against.
    return [f"{RENDERER_DIST}=={RENDERER_VERSION}"] + [
        f"{name}=={md.version(name)}" for name in DEPS
    ]


def is_managed_wheel(name: str) -> bool:
    """True for wheels this script downloads (renderer + deps), not the front-end."""
    low = name.lower()
    return low.startswith(f"{RENDERER_PREFIX}-") or any(low.startswith(f"{d}-") for d in DEPS)


def clear_managed_wheels() -> None:
    for whl in WHEELS.glob("*.whl"):
        if is_managed_wheel(whl.name):
            whl.unlink()


def download_wheels() -> None:
    specs = download_specs()
    for py, abi in PYTHONS:
        for _label, plat_tags in TARGETS:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--no-deps",
                "--python-version",
                py,
                "--implementation",
                "cp",
                "--abi",
                abi,
                "-d",
                str(WHEELS),
            ]
            for tag in plat_tags:
                cmd += ["--platform", tag]
            cmd += specs
            print("+", " ".join(cmd))
            subprocess.run(cmd, check=True)


def write_manifest(wheel_names: list[str]) -> None:
    entries = sorted(set(wheel_names))
    block = "\n".join(["wheels = ["] + [f'    "./wheels/{name}",' for name in entries] + ["]"])
    text = MANIFEST.read_text(encoding="utf-8")
    new_text, n = re.subn(r"wheels = \[.*?\]", block, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit("Could not find a 'wheels = [...]' block in the manifest")
    MANIFEST.write_text(new_text, encoding="utf-8")


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    ensure_pip()
    WHEELS.mkdir(parents=True, exist_ok=True)
    clear_managed_wheels()
    download_wheels()

    all_wheels = [whl.name for whl in WHEELS.glob("*.whl")]
    write_manifest(all_wheels)

    renderer = [n for n in all_wheels if n.lower().startswith(f"{RENDERER_PREFIX}-")]
    deps = [n for n in all_wheels if any(n.lower().startswith(f"{d}-") for d in DEPS)]
    frontend = [n for n in all_wheels if n.lower().startswith(f"{FRONTEND_PREFIX}-")]
    print(
        f"\nManifest updated: {len(set(all_wheels))} wheels "
        f"({len(renderer)} renderer + {len(frontend)} front-end + {len(deps)} deps)."
    )
    if not frontend:
        print(
            f"\nWARNING: no {FRONTEND_PREFIX}-*.whl found in {WHEELS.relative_to(REPO)}/; "
            "build it with `uv build --wheel` and copy it in before `extension build`."
        )


if __name__ == "__main__":
    main()
