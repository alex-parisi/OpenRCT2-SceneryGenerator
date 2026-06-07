"""
Scenery dataclasses. Rendering primitives (Model, MeshFrame, IndexedImage,
Light) come from openrct2_x7_renderer.types.
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

    # Render scale: OBJ units per OpenRCT2 tile (drives sprite size + the OBJ-space
    # tile-anchor maths). TILE_SIZE matches RCT2's real-world tile.
    units_per_tile: float = TILE_SIZE

    # Gameplay / placement.
    price: float = 1.0
    removal_price: float = 1.0
    cursor: str = DEFAULT_CURSOR
    height: int = DEFAULT_HEIGHT
    shape: str = "4/4"
    scenery_group: str = ""

    # Behaviour flags (map to object.json booleans).
    is_rotatable: bool = True
    is_stackable: bool = False
    requires_flat_surface: bool = False
    prohibit_walls: bool = False
    is_tree: bool = False

    # Colour remap. hasPrimaryColour is implied by a remappable material;
    # secondary adds a second remap region / overlay set of sprites.
    has_primary_colour: bool = False
    has_secondary_colour: bool = False

    # Frame animation (generic frameOffsets path; SmallSceneryObject.cpp:252).
    # When is_animated, `model` holds one pose per group; `frame_offsets` maps a
    # logical frame number to a pose group, and the engine cycles frames as
    # `(tick >> delay) & mask`. See `num_pose_groups`.
    is_animated: bool = False
    animation_delay: int = 0
    animation_mask: int = 0
    num_frames: int = 0
    frame_offsets: list[int] = field(default_factory=list)

    # Geometry: meshes + a Model placing them on the tile. For static scenery
    # each mesh entry has a single MeshFrame; for animated scenery each entry
    # has `num_pose_groups` frames (one per pose).
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
        `frame_offsets[frame] * 4 + direction` index hardcodes the * 4)."""
        if not self.is_animated or not self.frame_offsets:
            return 1
        return max(self.frame_offsets) + 1


@dataclass
class LargeSceneryTile:
    # Offsets in OpenRCT2 tile coords (x, y horizontal; z height) and clearance.
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

    # Render scale: OBJ units per OpenRCT2 tile (see SmallScenery).
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

    # Render scale: OBJ units per OpenRCT2 tile (see SmallScenery).
    units_per_tile: float = TILE_SIZE

    # Gameplay / placement. Banners have no removal price or cursor in object.json
    # (BannerObject::ReadJson reads only scrollingMode, price, flags, sceneryGroup).
    price: float = 1.0
    scrolling_mode: int = SCROLLING_MODE_NONE
    scenery_group: str = ""

    has_primary_colour: bool = False

    # Geometry. The mesh is split into a back-pole layer (faces tagged `Back`) and
    # a front layer (the front pole + sign; everything else), drawn as two sprites
    # per direction so the engine can occlude between them (Paint.Banner.cpp:107).
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

    # Render scale: OBJ units per OpenRCT2 tile (see SmallScenery).
    units_per_tile: float = TILE_SIZE

    price: float = 1.0
    cursor: str = PATH_ADDITION_DEFAULT_CURSOR
    scenery_group: str = ""

    # How the engine draws & indexes the sprites: one of PATH_ADDITION_RENDER_TYPES.
    render_as: str = "lamp"

    # Behaviour flags (map to object.json booleans). isAllowedOnQueue/Slope are
    # stored inverted in the engine but exposed here in the positive sense.
    is_breakable: bool = False
    is_jumping_fountain_water: bool = False
    is_jumping_fountain_snow: bool = False
    is_allowed_on_queue: bool = True
    is_allowed_on_slope: bool = True
    is_television: bool = False

    # Geometry: the normal object, plus optional vandalised ("broken") and, for
    # bins, "full" variants. Each is a separate mesh set + Model placement; when a
    # variant is absent the exporter reuses the normal edge sprites for its slots.
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
        Fountains never do (Paint.PathAddition.cpp)."""
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
        lamp/bench: 5 or 9; bin: 13; fountain: 5 (matches vanilla objects)."""
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

    # A scenery group has no geometry; `units_per_tile` exists only so it satisfies
    # the CLI's _SceneryObject protocol (a render Context is still constructed but
    # never used for groups).
    units_per_tile: float = TILE_SIZE

    priority: int = SCENERY_GROUP_DEFAULT_PRIORITY
    entries: list[str] = field(default_factory=list)

    # The tab icon, drawn from a provided PNG. The engine's DrawPreview reads
    # image+1 (SceneryGroupObject.cpp:77), so the exporter emits two icon slots.
    preview: IndexedImage | None = None


@dataclass
class WallScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    # Render scale: OBJ units per OpenRCT2 tile (see SmallScenery).
    units_per_tile: float = TILE_SIZE

    price: float = 1.0
    cursor: str = WALL_DEFAULT_CURSOR
    # `height` is in wall height units; the engine renders it `height * 8`
    # coordinate units tall.
    height: int = 1
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
        """Sprite count by capability. Doors use their own animation layout
        (handled separately).

        Glass and double-sided both force the full 6-slot block layout because
        the engine reads their second block at a hardcoded `imageIndex + 6`
        (Paint.Wall.cpp:148 glass overlay, :236-262 rear directions): 6 base
        sprites + 6 second-block sprites = 12. Otherwise it's the plain flat (2)
        or slope (6) block. The glass x double-sided `+12` combo is unsupported
        (the exporter refuses it), so the two never stack."""
        if self.has_glass or self.is_double_sided:
            return 12
        return 6 if self.is_allowed_on_slope else 2
