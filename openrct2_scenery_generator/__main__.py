"""
Usage:
    openrct2-scenery-generator [--test|--skip-render] <input.json|.yaml>
    python -m openrct2_scenery_generator [--test|--skip-render] <input.json|.yaml>
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from openrct2_object_common.cli import make_context, output_directory_of, run_cli
from openrct2_x7_renderer.types import Light

from .exporter import (
    export_banner,
    export_banner_test,
    export_large_scenery,
    export_large_scenery_test,
    export_path_addition,
    export_path_addition_test,
    export_scenery_group,
    export_scenery_group_test,
    export_small_scenery,
    export_small_scenery_test,
    export_wall_scenery,
    export_wall_scenery_test,
)
from .loader import (
    load_banner,
    load_large_scenery,
    load_path_addition,
    load_scenery_group,
    load_small_scenery,
    load_wall_scenery,
    object_type_of,
)


class _SceneryObject(Protocol):
    """The common surface the CLI needs from a loaded scenery object."""

    units_per_tile: float


_Loader = Callable[[Path], _SceneryObject]
_Exporter = Callable[..., None]

# object_type -> (load, export, export_test)
_DISPATCH: dict[str, tuple[_Loader, _Exporter, _Exporter]] = {
    "scenery_large": (load_large_scenery, export_large_scenery, export_large_scenery_test),
    "scenery_wall": (load_wall_scenery, export_wall_scenery, export_wall_scenery_test),
    "scenery_small": (load_small_scenery, export_small_scenery, export_small_scenery_test),
    "footpath_banner": (load_banner, export_banner, export_banner_test),
    "footpath_item": (load_path_addition, export_path_addition, export_path_addition_test),
    "scenery_group": (load_scenery_group, export_scenery_group, export_scenery_group_test),
}


def _render(args: argparse.Namespace, root: dict[str, Any], lights: list[Light]) -> None:
    load, export, export_test = _DISPATCH[object_type_of(root)]
    obj = load(args.input)
    context = make_context(lights, obj.units_per_tile, False)
    if args.test:
        export_test(obj, context)
    else:
        export(obj, context, output_directory_of(root), skip_render=args.skip_render)


def main(argv: list[str] | None = None) -> int:
    return run_cli("openrct2-scenery-generator", argv, _render)


if __name__ == "__main__":
    sys.exit(main())
