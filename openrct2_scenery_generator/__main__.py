"""
Usage:
    openrct2-scenery-generator [--test|--skip-render] <input.json|.yaml>
    python -m openrct2_scenery_generator [--test|--skip-render] <input.json|.yaml>
"""

import sys

from openrct2_object_common.dispatch import Dispatch, run_dispatch_cli

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

# object_type -> (load, export, export_test)
_DISPATCH: Dispatch = {
    "scenery_large": (load_large_scenery, export_large_scenery, export_large_scenery_test),
    "scenery_wall": (load_wall_scenery, export_wall_scenery, export_wall_scenery_test),
    "scenery_small": (load_small_scenery, export_small_scenery, export_small_scenery_test),
    "footpath_banner": (load_banner, export_banner, export_banner_test),
    "footpath_item": (load_path_addition, export_path_addition, export_path_addition_test),
    "scenery_group": (load_scenery_group, export_scenery_group, export_scenery_group_test),
}


def main(argv: list[str] | None = None) -> int:
    return run_dispatch_cli("openrct2-scenery-generator", argv, _DISPATCH, object_type_of)


if __name__ == "__main__":
    sys.exit(main())
