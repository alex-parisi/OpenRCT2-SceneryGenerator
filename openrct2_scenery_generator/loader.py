"""
Load a scenery config (JSON or YAML) into a SmallScenery dataclass.
"""

from pathlib import Path
from typing import Any

from openrct2_object_common.config import (
    LoadError,
    as_array_or_wrap,
    load_meshes,
    load_preview,
    optional_bool,
    optional_int,
    optional_number,
    optional_string,
    optional_string_list,
    parse_config,
    read_vector3,
    require_string,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.mesh import Mesh
from openrct2_x7_renderer.types import IndexedImage, MeshFrame, Model

from .constants import (
    DEFAULT_CURSOR,
    DEFAULT_HEIGHT,
    SCROLLING_MODE_NONE,
    SMALL_SCENERY_SHAPES,
    WALL_DEFAULT_CURSOR,
)
from .types import LargeScenery, LargeSceneryTile, SmallScenery, WallScenery


def _load_units_per_tile(root: dict[str, Any]) -> float:
    """Render scale: OBJ units per tile. Defaults to RCT2's real-world tile."""
    upt = optional_number(root, "units_per_tile", TILE_SIZE)
    if upt <= 0.0:
        raise LoadError('Property "units_per_tile" must be greater than 0')
    return upt


def _load_header(
    obj: SmallScenery | LargeScenery | WallScenery,
    root: dict[str, Any],
    preview: IndexedImage | None,
    cursor_default: str,
) -> None:
    """Populate the fields every scenery kind shares (identity, render scale,
    pricing, cursor, group). Kind-specific fields are loaded by the caller."""
    obj.id = require_string(root, "id")
    obj.original_id = optional_string(root, "original_id")
    obj.name = require_string(root, "name")
    obj.authors = optional_string_list(root, "authors")
    v_str = optional_string(root, "version")
    if v_str:
        obj.version = v_str
    obj.preview = preview if preview is not None else IndexedImage.blank(1, 1)

    obj.units_per_tile = _load_units_per_tile(root)
    obj.price = optional_number(root, "price", 1.0)
    obj.cursor = optional_string(root, "cursor", cursor_default)
    obj.scenery_group = optional_string(root, "scenery_group")


def _load_model(value: Any, num_meshes: int) -> Model:
    """Parse the single-frame `model` placement list into a Model."""
    if value is None:
        raise LoadError('Property "model" not found')
    arr = as_array_or_wrap(value)
    meshes_out: list[list[MeshFrame]] = []
    for elem in arr:
        if not isinstance(elem, dict):
            raise LoadError('Property "model" is not an object')

        mi = elem.get("mesh_index")
        if not isinstance(mi, int) or isinstance(mi, bool):
            raise LoadError('Property "mesh_index" not found or is not an integer')
        if mi >= num_meshes or mi < -1:
            raise LoadError(f"Mesh index {mi} is out of bounds")

        # MeshFrame is a frozen dataclass, so collect its fields and construct it
        # once (position/orientation default to zero vectors when absent).
        kwargs: dict[str, Any] = {"mesh_index": int(mi)}
        for key in ("position", "orientation"):
            prop = elem.get(key)
            if prop is not None:
                kwargs[key] = read_vector3(prop)

        meshes_out.append([MeshFrame(**kwargs)])
    return Model(meshes=meshes_out)


def _load_animated_model(frames_value: Any, num_meshes: int) -> Model:
    """Parse a list of poses into a Model whose mesh entries each carry one
    MeshFrame per pose. Every pose must list the same model entries in order;
    they are transposed so `model.meshes[i][g]` is entry i in pose group g."""
    if not isinstance(frames_value, list) or len(frames_value) == 0:
        raise LoadError('Property "animation.frames" not found or is not a non-empty array')
    poses = [_load_model(p, num_meshes) for p in frames_value]
    n = len(poses[0].meshes)
    for p in poses:
        if len(p.meshes) != n:
            raise LoadError("All animation frames must list the same number of model entries")
    meshes_out = [[poses[g].meshes[i][0] for g in range(len(poses))] for i in range(n)]
    return Model(meshes=meshes_out)


def _load_animation(obj: SmallScenery, anim: Any) -> None:
    """Populate the animation fields + the per-pose Model from an `animation`
    config block."""
    if not isinstance(anim, dict):
        raise LoadError('Property "animation" is not an object')
    obj.is_animated = True
    obj.animation_delay = optional_int(anim, "delay", 0)
    obj.animation_mask = optional_int(anim, "mask", 0)

    fo = anim.get("frame_offsets")
    if not isinstance(fo, list) or len(fo) == 0:
        raise LoadError('Property "animation.frame_offsets" not found or is not a non-empty array')
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in fo):
        raise LoadError('Property "animation.frame_offsets" must be non-negative integers')
    obj.frame_offsets = list(fo)
    obj.num_frames = optional_int(anim, "num_frames", len(fo))

    obj.model = _load_animated_model(anim.get("frames"), len(obj.meshes))
    if len(obj.model.meshes) and len(obj.model.meshes[0]) != obj.num_pose_groups:
        raise LoadError(
            f"animation.frames lists {len(obj.model.meshes[0])} poses but frame_offsets "
            f"references {obj.num_pose_groups} (max offset + 1)"
        )


def build_small_scenery(
    config: dict[str, Any], meshes: list[Mesh], preview: IndexedImage | None = None
) -> SmallScenery:
    """Build a SmallScenery from a parsed config dict + in-memory meshes."""
    root = config
    obj = SmallScenery()
    _load_header(obj, root, preview, DEFAULT_CURSOR)

    obj.removal_price = optional_number(root, "removal_price", obj.price)
    obj.height = optional_int(root, "height", DEFAULT_HEIGHT)

    obj.shape = optional_string(root, "shape", "4/4")
    if obj.shape not in SMALL_SCENERY_SHAPES:
        raise LoadError(
            f'Unrecognized shape "{obj.shape}" (expected one of {SMALL_SCENERY_SHAPES})'
        )

    obj.is_rotatable = optional_bool(root, "is_rotatable", True)
    obj.is_stackable = optional_bool(root, "is_stackable", False)
    obj.requires_flat_surface = optional_bool(root, "requires_flat_surface", False)
    obj.prohibit_walls = optional_bool(root, "prohibit_walls", False)
    obj.is_tree = optional_bool(root, "is_tree", False)
    obj.has_primary_colour = optional_bool(root, "has_primary_colour", False)
    obj.has_secondary_colour = optional_bool(root, "has_secondary_colour", False)

    obj.meshes = list(meshes)
    anim = root.get("animation")
    if anim is not None:
        _load_animation(obj, anim)
    else:
        obj.model = _load_model(root.get("model"), len(obj.meshes))
    return obj


def load_small_scenery(json_path: Path | str) -> SmallScenery:
    """Parse a config file, load its meshes + preview, build a SmallScenery."""
    root = parse_config(json_path)
    return build_small_scenery(root, load_meshes(root), load_preview(root))


def _load_tiles(value: Any) -> list[LargeSceneryTile]:
    if not isinstance(value, list) or len(value) == 0:
        raise LoadError('Property "tiles" not found or is not a non-empty array')
    tiles: list[LargeSceneryTile] = []
    for jt in value:
        if not isinstance(jt, dict):
            raise LoadError('Each "tiles" element must be an object')
        tiles.append(
            LargeSceneryTile(
                x=optional_int(jt, "x", 0),
                y=optional_int(jt, "y", 0),
                z=optional_int(jt, "z", 0),
                clearance=optional_int(jt, "clearance", 0),
                has_supports=optional_bool(jt, "has_supports", False),
                allow_supports_above=optional_bool(jt, "allow_supports_above", False),
                corners=optional_int(jt, "corners", 0xF),
                walls=optional_int(jt, "walls", 0),
            )
        )
    return tiles


def build_large_scenery(
    config: dict[str, Any], meshes: list[Mesh], preview: IndexedImage | None = None
) -> LargeScenery:
    """Build a LargeScenery from a parsed config dict + in-memory meshes."""
    root = config
    obj = LargeScenery()
    _load_header(obj, root, preview, DEFAULT_CURSOR)

    obj.removal_price = optional_number(root, "removal_price", obj.price)
    obj.scrolling_mode = optional_int(root, "scrolling_mode", SCROLLING_MODE_NONE)

    obj.has_primary_colour = optional_bool(root, "has_primary_colour", False)
    obj.has_secondary_colour = optional_bool(root, "has_secondary_colour", False)
    obj.has_tertiary_colour = optional_bool(root, "has_tertiary_colour", False)
    obj.is_tree = optional_bool(root, "is_tree", False)
    obj.is_photogenic = optional_bool(root, "is_photogenic", False)

    obj.tiles = _load_tiles(root.get("tiles"))

    obj.meshes = list(meshes)
    obj.model = _load_model(root.get("model"), len(obj.meshes))
    return obj


def load_large_scenery(json_path: Path | str) -> LargeScenery:
    root = parse_config(json_path)
    return build_large_scenery(root, load_meshes(root), load_preview(root))


def build_wall_scenery(
    config: dict[str, Any], meshes: list[Mesh], preview: IndexedImage | None = None
) -> WallScenery:
    """Build a WallScenery from a parsed config dict + in-memory meshes."""
    root = config
    obj = WallScenery()
    _load_header(obj, root, preview, WALL_DEFAULT_CURSOR)

    obj.height = optional_int(root, "height", 1)
    obj.scrolling_mode = optional_int(root, "scrolling_mode", SCROLLING_MODE_NONE)

    obj.has_primary_colour = optional_bool(root, "has_primary_colour", False)
    obj.has_secondary_colour = optional_bool(root, "has_secondary_colour", False)
    obj.has_tertiary_colour = optional_bool(root, "has_tertiary_colour", False)
    obj.is_allowed_on_slope = optional_bool(root, "is_allowed_on_slope", False)
    obj.has_glass = optional_bool(root, "has_glass", False)
    obj.is_double_sided = optional_bool(root, "is_double_sided", False)
    obj.is_door = optional_bool(root, "is_door", False)
    obj.is_long_door_animation = optional_bool(root, "is_long_door_animation", False)
    obj.is_animated = optional_bool(root, "is_animated", False)
    obj.is_opaque = optional_bool(root, "is_opaque", False)
    ds = root.get("door_sound")
    if ds is not None:
        obj.door_sound = optional_int(root, "door_sound", 0)

    obj.meshes = list(meshes)
    obj.model = _load_model(root.get("model"), len(obj.meshes))
    return obj


def load_wall_scenery(json_path: Path | str) -> WallScenery:
    root = parse_config(json_path)
    return build_wall_scenery(root, load_meshes(root), load_preview(root))


def object_type_of(config: dict[str, Any]) -> str:
    """Read the scenery object type, defaulting to small scenery."""
    t = optional_string(config, "object_type", "scenery_small")
    if t not in ("scenery_small", "scenery_large", "scenery_wall"):
        raise LoadError(f'Unrecognized object_type "{t}"')
    return t
