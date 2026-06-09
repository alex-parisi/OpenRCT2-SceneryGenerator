"""
Scenery-specific constants. Shared rendering constants live in
openrct2_x7_renderer.constants.
"""

from openrct2_x7_renderer.constants import TILE_SIZE as TILE_SIZE  # noqa: F401

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

# Default cursor for path additions (PathAdditionObject.cpp -> CursorID::LamppostDown).
PATH_ADDITION_DEFAULT_CURSOR = "CURSOR_LAMPPOST_DOWN"

# How a path addition is drawn, as accepted by object.json `properties.renderAs`
# (PathAdditionObject::ParseDrawType). "lamp" is the engine default.
PATH_ADDITION_RENDER_TYPES = ["lamp", "bin", "bench", "fountain"]

# Default scenery-group sort priority (SceneryGroupObject::ReadJson default).
SCENERY_GROUP_DEFAULT_PRIORITY = 40

# Animated walls cycle a fixed 8 frames: the engine indexes
# `image + imageOffset + (currentTicks & 7) * 2` (Paint.Wall.cpp PaintWallWall),
# so the tick counter masks to 8 frames and each frame is 2 image slots apart.
# That `* 2` stride collides with the slope image offsets (2..5), so an animated
# wall is necessarily FLAT-only: 8 frames x 2 flat sprites = 16 images.
WALL_ANIMATION_FRAMES = 8

# Door walls have a fixed 36-image table (Paint.Wall.cpp PaintWallDoor +
# DirectionToDoorImageOffset): 9 swing "groups" x 2 screen orientations (the two
# diagonals, like a flat wall's pair) x 2 sub-images (the engine draws each pose
# as a base image + the next index, with its own hardcoded bounding boxes). The 9
# groups are a closed pose, 4 forward-swing poses, then 4 backward-swing poses
# (the door opens whichever way away from whoever approaches). We sample the
# closed + 4 forward poses from the author's keyframes and mirror those 4 for the
# backward swing.
DOOR_SAMPLE_FRAMES = 5
DOOR_NUM_IMAGES = 36
