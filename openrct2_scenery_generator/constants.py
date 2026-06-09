"""
Scenery-specific constants.
Shared rendering constants live in openrct2_x7_renderer.constants.
"""

from openrct2_x7_renderer.constants import TILE_SIZE as TILE_SIZE  # noqa: F401

# Small-scenery footprint shapes
SMALL_SCENERY_SHAPES = [
    "1/4",
    "2/4",
    "3/4",
    "4/4",
    "1/4+D",
    "4/4+D",
]

# Default mouse cursor for placing the object
DEFAULT_CURSOR = "CURSOR_STATUE_DOWN"

# `height` is OpenRCT2's clearance in Z coordinate units (8 units per tile
# height step)
DEFAULT_HEIGHT = 64

# OpenRCT2 world coordinate units per tile
COORDS_PER_TILE = 32

# OpenRCT2's "no scrolling text" sentinel
SCROLLING_MODE_NONE = 255

# Default cursor for wall objects
WALL_DEFAULT_CURSOR = "CURSOR_FENCE_DOWN"

# Default cursor for path additions
PATH_ADDITION_DEFAULT_CURSOR = "CURSOR_LAMPPOST_DOWN"

# How a path addition is drawn
PATH_ADDITION_RENDER_TYPES = ["lamp", "bin", "bench", "fountain"]

# Default scenery-group sort priority
SCENERY_GROUP_DEFAULT_PRIORITY = 40

# Animated walls cycle a fixed 8 frames
WALL_ANIMATION_FRAMES = 8

# Door walls have a fixed 36-image table
DOOR_SAMPLE_FRAMES = 5
DOOR_NUM_IMAGES = 36
