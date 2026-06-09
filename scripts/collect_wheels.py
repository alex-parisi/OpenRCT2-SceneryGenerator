#!/usr/bin/env python3

"""
Bundle the Blender add-on's wheels and regenerate the manifest.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import subprocess
import sys

from _buildlib import (
    ADDONS,
    DEPS,
    FRONTEND_PREFIX,
    OBJECTCOMMON_PREFIX,
    RENDERER_PREFIX,
    REPO,
    objectcommon_spec,
    pip_download_cmd,
    renderer_spec,
    run,
    set_toml_array,
    wheels_block,
)

ADDON = REPO / ADDONS["scenery"]
WHEELS = ADDON / "wheels"
MANIFEST = ADDON / "blender_manifest.toml"

PYTHONS = (("3.11", "cp311"), ("3.13", "cp313"))

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
    return [renderer_spec(), objectcommon_spec()] + [
        f"{name}=={md.version(name)}" for name in DEPS
    ]


def is_managed_wheel(name: str) -> bool:
    low = name.lower()
    return (
        low.startswith(f"{RENDERER_PREFIX}-")
        or low.startswith(f"{OBJECTCOMMON_PREFIX}-")
        or any(low.startswith(f"{d}-") for d in DEPS)
    )


def clear_managed_wheels() -> None:
    for whl in WHEELS.glob("*.whl"):
        if is_managed_wheel(whl.name):
            whl.unlink()


def download_wheels() -> None:
    specs = download_specs()
    pip_prefix = [sys.executable, "-m", "pip"]
    for py, abi in PYTHONS:
        for _label, plat_tags in TARGETS:
            run(
                pip_download_cmd(
                    pip_prefix,
                    dest=WHEELS,
                    py_version=py,
                    abi=abi,
                    platform_tags=plat_tags,
                    specs=specs,
                )
            )


def write_manifest(wheel_names: list[str]) -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    MANIFEST.write_text(set_toml_array(text, "wheels", wheels_block(wheel_names)), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--addon", choices=ADDONS, default="scenery", help="which add-on's wheels/ to populate"
    )
    args = ap.parse_args()
    global ADDON, WHEELS, MANIFEST
    ADDON = REPO / ADDONS[args.addon]
    WHEELS = ADDON / "wheels"
    MANIFEST = ADDON / "blender_manifest.toml"

    ensure_pip()
    WHEELS.mkdir(parents=True, exist_ok=True)
    clear_managed_wheels()
    download_wheels()

    all_wheels = [whl.name for whl in WHEELS.glob("*.whl")]
    write_manifest(all_wheels)

    renderer = [n for n in all_wheels if n.lower().startswith(f"{RENDERER_PREFIX}-")]
    objectcommon = [n for n in all_wheels if n.lower().startswith(f"{OBJECTCOMMON_PREFIX}-")]
    deps = [n for n in all_wheels if any(n.lower().startswith(f"{d}-") for d in DEPS)]
    frontend = [n for n in all_wheels if n.lower().startswith(f"{FRONTEND_PREFIX}-")]
    print(
        f"\nManifest updated: {len(set(all_wheels))} wheels "
        f"({len(renderer)} renderer + {len(objectcommon)} shared + "
        f"{len(frontend)} front-end + {len(deps)} deps)."
    )
    if not frontend:
        print(
            f"\nWARNING: no {FRONTEND_PREFIX}-*.whl found in {WHEELS.relative_to(REPO)}/; "
            "build it with `uv build --wheel` and copy it in before `extension build`."
        )


if __name__ == "__main__":
    main()
