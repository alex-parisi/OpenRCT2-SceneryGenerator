"""
OpenRCT2 scenery object generator. Builds `scenery_small`, `scenery_large`,
`scenery_wall`, `footpath_banner`, and `footpath_item` `.parkobj`s from OBJ meshes
using the shared iso-render core, plus `scenery_group` tabs (icon + member list).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("OpenRCT2-SceneryGenerator")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0.0.0"
