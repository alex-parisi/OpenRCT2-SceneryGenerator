"""
Scenery dataclasses.
Rendering primitives come from openrct2_x7_renderer.types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.types import IndexedImage, Model

if TYPE_CHECKING:
    from openrct2_x7_renderer.mesh import Mesh

from .constants import (
    DEFAULT_CURSOR,
    DEFAULT_HEIGHT,
    PATH_ADDITION_DEFAULT_CURSOR,
    SCENERY_GROUP_DEFAULT_PRIORITY,
    SCROLLING_MODE_NONE,
    WALL_DEFAULT_CURSOR,
)


@dataclass
class SmallScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    # Gameplay / placement.
    price: float = 1.0
    removal_price: float = 1.0
    cursor: str = DEFAULT_CURSOR
    height: int = DEFAULT_HEIGHT
    shape: str = "4/4"
    scenery_group: str = ""

    # Behaviour flags
    is_rotatable: bool = True
    is_stackable: bool = False
    requires_flat_surface: bool = False
    prohibit_walls: bool = False
    is_tree: bool = False
    # Engine VOFFSET_CENTRE: paint with a near-full-tile bounding box (and a
    # tile-corner anchor). Vanilla sets this on diagonal walls and other
    # wall-like full-tile pieces so they sort correctly.
    voffset_centre: bool = False

    # Color remap
    has_primary_colour: bool = False
    has_secondary_colour: bool = False
    has_tertiary_colour: bool = False

    # Frame animation
    is_animated: bool = False
    animation_delay: int = 0
    animation_mask: int = 0
    num_frames: int = 0
    frame_offsets: list[int] = field(default_factory=list)

    # Geometry
    meshes: list[Mesh] = field(default_factory=list)
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_rotations(self) -> int:
        return 4 if self.is_rotatable else 1

    @property
    def num_pose_groups(self) -> int:
        """Distinct sprite groups an animated object needs: one per referenced
        pose. Each group is rendered as 4 rotation sprites (the engine's
        frame_offsets[frame] * 4 + direction index hardcodes the * 4)."""
        if not self.is_animated or not self.frame_offsets:
            return 1
        return max(self.frame_offsets) + 1


@dataclass
class LargeSceneryTile:
    # Offsets in OpenRCT2 tile coordinates and clearance
    x: int = 0
    y: int = 0
    z: int = 0
    clearance: int = 0
    has_supports: bool = False
    allow_supports_above: bool = False
    corners: int = 0xF
    walls: int = 0


@dataclass
class LargeScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    price: float = 1.0
    removal_price: float = 1.0
    cursor: str = DEFAULT_CURSOR
    scrolling_mode: int = SCROLLING_MODE_NONE
    scenery_group: str = ""

    has_primary_colour: bool = False
    has_secondary_colour: bool = False
    has_tertiary_colour: bool = False
    is_tree: bool = False
    is_photogenic: bool = False

    tiles: list[LargeSceneryTile] = field(default_factory=list)

    meshes: list[Mesh] = field(default_factory=list)
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_tiles(self) -> int:
        return len(self.tiles)


@dataclass
class Banner:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    # Banners have no removal price or cursor
    price: float = 1.0
    scrolling_mode: int = SCROLLING_MODE_NONE
    scenery_group: str = ""

    has_primary_colour: bool = False

    # Geometry
    meshes: list[Mesh] = field(default_factory=list)
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_sprites(self) -> int:
        """4 directions x (back pole, front pole + sign)."""
        return 8


@dataclass
class PathAddition:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    price: float = 1.0
    cursor: str = PATH_ADDITION_DEFAULT_CURSOR
    scenery_group: str = ""

    render_as: str = "lamp"

    # Behaviour flags
    is_breakable: bool = False
    is_jumping_fountain_water: bool = False
    is_jumping_fountain_snow: bool = False
    is_allowed_on_queue: bool = True
    is_allowed_on_slope: bool = True
    is_television: bool = False

    # Geometry: the normal object, plus optional vandalised ("broken") and, for
    # bins, "full" variants
    meshes: list[Mesh] = field(default_factory=list)
    model: Model = field(default_factory=Model)
    broken_meshes: list[Mesh] = field(default_factory=list)
    broken_model: Model = field(default_factory=Model)
    full_meshes: list[Mesh] = field(default_factory=list)
    full_model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def needs_broken(self) -> bool:
        """Bins always carry broken sprites; lamps/benches only when breakable.
        Fountains never do"""
        if self.render_as == "bin":
            return True
        return self.is_breakable and self.render_as in ("lamp", "bench")

    @property
    def needs_full(self) -> bool:
        """Only bins carry "full" sprites."""
        return self.render_as == "bin"

    @property
    def num_sprites(self) -> int:
        """1 menu preview + 4 edge sprites, then +4 per broken/full block.
        lamp/bench: 5 or 9; bin: 13; fountain: 5"""
        n = 1 + 4
        if self.needs_broken:
            n += 4
        if self.needs_full:
            n += 4
        return n


@dataclass
class SceneryGroup:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    priority: int = SCENERY_GROUP_DEFAULT_PRIORITY
    entries: list[str] = field(default_factory=list)

    # The tab icon, drawn from a provided PNG
    preview: IndexedImage | None = None


@dataclass
class WallScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    units_per_tile: float = TILE_SIZE

    price: float = 1.0
    cursor: str = WALL_DEFAULT_CURSOR
    height: int = 1  # in wall height units
    scrolling_mode: int = SCROLLING_MODE_NONE
    scenery_group: str = ""

    has_primary_colour: bool = False
    has_secondary_colour: bool = False
    has_tertiary_colour: bool = False

    is_allowed_on_slope: bool = False
    has_glass: bool = False
    is_double_sided: bool = False
    is_door: bool = False
    is_long_door_animation: bool = False
    is_animated: bool = False
    is_opaque: bool = False
    door_sound: int | None = None

    meshes: list[Mesh] = field(default_factory=list)
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_sprites(self) -> int:
        """Sprite count by capability"""
        if self.has_glass or self.is_double_sided:
            return 12
        return 6 if self.is_allowed_on_slope else 2
