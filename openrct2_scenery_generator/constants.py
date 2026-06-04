"""
Scenery-specific constants. Shared rendering constants live in
openrct2_x7_renderer.constants.
"""

# Small-scenery footprint shapes, as accepted by OpenRCT2's object.json
# `properties.shape`. "n/4" is the number of occupied tile quadrants; "+D"
# marks a full-tile diagonal variant.
SMALL_SCENERY_SHAPES = [
    "1/4",
    "2/4",
    "3/4",
    "4/4",
    "1/4+D",
    "4/4+D",
]

# Default mouse cursor for placing the object. OpenRCT2 accepts a `CURSOR_*`
# string; we pass it through and only default it.
DEFAULT_CURSOR = "CURSOR_STATUE_DOWN"

# `height` is OpenRCT2's clearance in Z coordinate units (8 units per tile
# height step). This is a gameplay value, independent of the rendered sprite.
DEFAULT_HEIGHT = 64

# OpenRCT2 world coordinate units per tile. Large-scenery `tiles[].x/y` in the
# object.json are stored in coordinate units (0, 32, 64, ...), so a tile index
# `n` in the config maps to `n * COORDS_PER_TILE`.
COORDS_PER_TILE = 32

# OpenRCT2's "no scrolling text" sentinel (ScrollingText.h kScrollingModeNone).
# Scrolling mode 0 is a *valid, active* mode, so a plain object must use 255 or
# the engine paints garbage scrolling text over it.
SCROLLING_MODE_NONE = 255

# Default cursor for wall objects (WallObject.cpp -> CursorID::FenceDown).
WALL_DEFAULT_CURSOR = "CURSOR_FENCE_DOWN"
