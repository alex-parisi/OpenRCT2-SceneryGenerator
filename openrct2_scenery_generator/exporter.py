"""
Build object.json and assemble the scenery .parkobj ZIP.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from openrct2_object_common.objectjson import object_json_header
from openrct2_object_common.parkobj import (
    assemble_parkobj,
    combine_indexed_images,
    write_images_dat_lgx,
)
from openrct2_object_common.placement import add_model_to_scene
from openrct2_x7_renderer.geometry import combine_model_world
from openrct2_x7_renderer.image import write_png
from openrct2_x7_renderer.ray_trace import VIEWS, Context
from openrct2_x7_renderer.types import IndexedImage

from .constants import COORDS_PER_TILE, SCROLLING_MODE_NONE
from .sprite_renderer import (
    render_banner,
    render_large_scenery,
    render_path_addition,
    render_small_scenery,
    render_small_scenery_anchored,
    render_small_scenery_animated,
    render_wall,
    render_wall_animated,
    render_wall_door,
    small_scenery_paint_anchor,
)
from .types import (
    Banner,
    LargeScenery,
    PathAddition,
    SceneryGroup,
    SmallScenery,
    WallScenery,
)

log = logging.getLogger(__name__)

Scenery = SmallScenery | LargeScenery | WallScenery | Banner | PathAddition | SceneryGroup
ProgressFn = Callable[[int, int], None]
RenderSprites = Callable[[Any, Context, Path, ProgressFn | None], list[str]]


def build_small_scenery_json(obj: SmallScenery) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="scenery_small",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )

    properties: dict[str, Any] = {
        "price": obj.price,
        "removalPrice": obj.removal_price,
        "cursor": obj.cursor,
        "height": obj.height,
        "shape": obj.shape,
        "requiresFlatSurface": obj.requires_flat_surface,
        "isRotatable": obj.is_rotatable,
        "isStackable": obj.is_stackable,
        "prohibitWalls": obj.prohibit_walls,
        "isTree": obj.is_tree,
        "hasPrimaryColour": obj.has_primary_colour,
        "hasSecondaryColour": obj.has_secondary_colour,
        "hasTertiaryColour": obj.has_tertiary_colour,
    }
    if obj.voffset_centre:
        properties["SMALL_SCENERY_FLAG_VOFFSET_CENTRE"] = True
    if obj.is_animated:
        properties["isAnimated"] = True
        properties["animationDelay"] = obj.animation_delay
        properties["animationMask"] = obj.animation_mask
        properties["numFrames"] = obj.num_frames
        properties["frameOffsets"] = list(obj.frame_offsets)
        properties["SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED"] = True
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _small_scenery_anchor(obj: SmallScenery) -> float | None:
    return small_scenery_paint_anchor(obj.shape, obj.voffset_centre, obj.prohibit_walls)


def _render_sprites(
    obj: SmallScenery,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    anchor = _small_scenery_anchor(obj)
    if obj.is_animated:
        images = render_small_scenery_animated(
            context, obj.meshes, obj.model, obj.num_pose_groups, progress,
            anchor=anchor, units_per_tile=obj.units_per_tile,
        )
    elif anchor is not None:
        combined = combine_model_world(obj.meshes, obj.model)
        images = render_small_scenery_anchored(
            context, combined, anchor, obj.num_rotations, obj.units_per_tile, progress
        )
    else:
        with context.begin_render() as scene:
            add_model_to_scene(scene, obj.meshes, obj.model, clamp_frame=True)
            with scene.finalize() as ready:
                images = render_small_scenery(
                    ready, num_rotations=obj.num_rotations, progress=progress
                )

    return write_images_dat_lgx(images, object_dir)


def _export_scenery(
    obj: Scenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    obj_json: dict[str, Any],
    render_sprites: RenderSprites,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    """Render the sprites (or reuse a previous render) and zip object.json +
    images.dat into the parkobj."""
    assemble_parkobj(
        obj_json,
        Path(parkobj_path),
        Path(work_dir),
        lambda wd: render_sprites(obj, context, wd, progress),
        skip_render=skip_render,
    )


def export_small_scenery_to(
    obj: SmallScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_small_scenery_json(obj), _render_sprites, skip_render, progress,
    )


def export_small_scenery(
    obj: SmallScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_small_scenery_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_small_scenery_test(
    obj: SmallScenery, context: Context, test_dir: Path | str = "test"
) -> None:
    """Single-viewpoint render per rotation (per pose group) for fast
    iteration."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    anchor = _small_scenery_anchor(obj)
    if obj.is_animated:
        images = render_small_scenery_animated(
            context, obj.meshes, obj.model, obj.num_pose_groups,
            anchor=anchor, units_per_tile=obj.units_per_tile,
        )
        for d in range(4):
            write_png(images[d], test_dir / f"base_{d}.png")
        for g in range(obj.num_pose_groups):
            for d in range(4):
                write_png(images[4 + g * 4 + d], test_dir / f"pose{g}_{d}.png")
        write_png(combine_indexed_images(images[:4]), test_dir / "preview_combined.png")
        return
    rotations: list[IndexedImage] = []
    if anchor is not None:
        combined = combine_model_world(obj.meshes, obj.model)
        rotations = render_small_scenery_anchored(
            context, combined, anchor, obj.num_rotations, obj.units_per_tile
        )
        for i, img in enumerate(rotations):
            write_png(img, test_dir / f"scenery_{i}.png")
    else:
        with context.begin_render() as scene:
            add_model_to_scene(scene, obj.meshes, obj.model, clamp_frame=True)
            with scene.finalize() as ready:
                for i in range(obj.num_rotations):
                    img = ready.render_view(VIEWS[i])
                    write_png(img, test_dir / f"scenery_{i}.png")
                    rotations.append(img)
    write_png(combine_indexed_images(rotations), test_dir / "preview_combined.png")


def _tile_centers_xz(obj: LargeScenery) -> NDArray[np.float64]:
    """Tile centers in OBJ horizontal (X, Z) units."""
    if not obj.tiles:
        return np.zeros((0, 2), dtype=np.float64)
    upt = obj.units_per_tile
    return np.array([[t.x * upt, t.y * upt] for t in obj.tiles], dtype=np.float64)


def build_large_scenery_json(obj: LargeScenery) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="scenery_large",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )

    properties: dict[str, Any] = {
        "price": obj.price,
        "removalPrice": obj.removal_price,
        "cursor": obj.cursor,
        "hasPrimaryColour": obj.has_primary_colour,
        "hasSecondaryColour": obj.has_secondary_colour,
        "hasTertiaryColour": obj.has_tertiary_colour,
        "isTree": obj.is_tree,
        "isPhotogenic": obj.is_photogenic,
        "tiles": [
            {
                "x": -t.x * COORDS_PER_TILE,
                "y": -t.y * COORDS_PER_TILE,
                "z": t.z,
                "clearance": t.clearance,
                "hasSupports": t.has_supports,
                "allowSupportsAbove": t.allow_supports_above,
                "corners": t.corners,
                "walls": t.walls,
            }
            for t in obj.tiles
        ],
    }
    if obj.scrolling_mode != SCROLLING_MODE_NONE:
        properties["scrollingMode"] = obj.scrolling_mode
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_large_sprites(
    obj: LargeScenery,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    combined = combine_model_world(obj.meshes, obj.model)
    centers = _tile_centers_xz(obj)
    images = render_large_scenery(context, combined, centers, obj.units_per_tile, progress)
    return write_images_dat_lgx(images, object_dir, note=f" for {obj.num_tiles} tiles")


def export_large_scenery_to(
    obj: LargeScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_large_scenery_json(obj), _render_large_sprites, skip_render, progress,
    )


def export_large_scenery(
    obj: LargeScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_large_scenery_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_large_scenery_test(
    obj: LargeScenery, context: Context, test_dir: Path | str = "test"
) -> None:
    """Render the per-tile sprites flat for fast iteration (4 dirs per tile)."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    combined = combine_model_world(obj.meshes, obj.model)
    centers = _tile_centers_xz(obj)
    images = render_large_scenery(context, combined, centers, obj.units_per_tile)
    for d in range(4):
        write_png(images[d], test_dir / f"preview_{d}.png")
    for seq in range(obj.num_tiles):
        for d in range(4):
            write_png(images[4 + seq * 4 + d], test_dir / f"tile{seq}_{d}.png")
    write_png(combine_indexed_images(images[:4]), test_dir / "preview_combined.png")


def build_wall_scenery_json(obj: WallScenery) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="scenery_wall",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )

    properties: dict[str, Any] = {
        "price": obj.price,
        "cursor": obj.cursor,
        "height": obj.height,
    }
    double_sided = obj.is_double_sided
    if double_sided and obj.has_glass:
        log.warning("glass + isDoubleSided combo is unsupported; ignoring isDoubleSided")
        double_sided = False

    allowed_on_slope = obj.is_allowed_on_slope
    has_glass = obj.has_glass
    is_animated = obj.is_animated
    if is_animated and (allowed_on_slope or has_glass or double_sided):
        log.warning(
            "animated walls are flat-only; ignoring isAllowedOnSlope/hasGlass/isDoubleSided"
        )
        allowed_on_slope = False
        has_glass = False
        double_sided = False

    if obj.is_door:
        if has_glass or double_sided or is_animated:
            log.warning("door walls ignore hasGlass / isDoubleSided / isAnimated")
        has_glass = False
        double_sided = False
        is_animated = False

    for key, val in (
        ("hasPrimaryColour", obj.has_primary_colour),
        ("hasSecondaryColour", obj.has_secondary_colour),
        ("hasTertiaryColour", obj.has_tertiary_colour),
        ("isAllowedOnSlope", allowed_on_slope),
        ("hasGlass", has_glass),
        ("isDoubleSided", double_sided),
        ("isDoor", obj.is_door),
        ("isLongDoorAnimation", obj.is_long_door_animation),
        ("isAnimated", is_animated),
        ("isOpaque", obj.is_opaque),
    ):
        if val:
            properties[key] = True
    if obj.scrolling_mode != SCROLLING_MODE_NONE:
        properties["scrollingMode"] = obj.scrolling_mode
    if obj.door_sound is not None:
        properties["doorSound"] = obj.door_sound
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_wall_sprites(
    obj: WallScenery,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    if obj.is_door:
        images = render_wall_door(
            context, obj.meshes, obj.model, obj.units_per_tile, progress
        )
        return write_images_dat_lgx(images, object_dir)
    if obj.is_animated:
        images = render_wall_animated(
            context, obj.meshes, obj.model, obj.units_per_tile, progress
        )
        return write_images_dat_lgx(images, object_dir)
    combined = combine_model_world(obj.meshes, obj.model)
    images = render_wall(
        context,
        combined,
        obj.is_allowed_on_slope,
        obj.has_glass,
        obj.is_double_sided,
        obj.units_per_tile,
    )
    if progress is not None:
        progress(1, 1)
    return write_images_dat_lgx(images, object_dir)


def export_wall_scenery_to(
    obj: WallScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_wall_scenery_json(obj), _render_wall_sprites, skip_render, progress,
    )


def export_wall_scenery(
    obj: WallScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_wall_scenery_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_wall_scenery_test(
    obj: WallScenery, context: Context, test_dir: Path | str = "test"
) -> None:
    """Render the wall sprites for fast iteration."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    combined = combine_model_world(obj.meshes, obj.model)
    images = render_wall(
        context,
        combined,
        obj.is_allowed_on_slope,
        obj.has_glass,
        obj.is_double_sided,
        obj.units_per_tile,
    )
    for i, img in enumerate(images):
        write_png(img, test_dir / f"wall_{i}.png")
    write_png(combine_indexed_images(images), test_dir / "preview_combined.png")


def build_banner_json(obj: Banner) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="footpath_banner",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )

    properties: dict[str, Any] = {"price": obj.price}
    if obj.has_primary_colour:
        properties["hasPrimaryColour"] = True
    if obj.scrolling_mode != SCROLLING_MODE_NONE:
        properties["scrollingMode"] = obj.scrolling_mode
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_banner_sprites(
    obj: Banner,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    combined = combine_model_world(obj.meshes, obj.model)
    images = render_banner(context, combined, obj.units_per_tile, progress)
    return write_images_dat_lgx(images, object_dir)


def export_banner_to(
    obj: Banner,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_banner_json(obj), _render_banner_sprites, skip_render, progress,
    )


def export_banner(
    obj: Banner, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_banner_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_banner_test(obj: Banner, context: Context, test_dir: Path | str = "test") -> None:
    """Render the banner sprites for fast iteration (back/front per direction)."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    combined = combine_model_world(obj.meshes, obj.model)
    images = render_banner(context, combined, obj.units_per_tile)
    for d in range(4):
        write_png(images[d * 2], test_dir / f"banner_{d}_back.png")
        write_png(images[d * 2 + 1], test_dir / f"banner_{d}_front.png")
    write_png(combine_indexed_images(images), test_dir / "preview_combined.png")


def build_path_addition_json(obj: PathAddition) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="footpath_item",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )

    properties: dict[str, Any] = {
        "renderAs": obj.render_as,
        "cursor": obj.cursor,
        "price": obj.price,
    }
    draw_flag = {"bin": "isBin", "bench": "isBench", "lamp": "isLamp"}.get(obj.render_as)
    if draw_flag is not None:
        properties[draw_flag] = True

    for key, val in (
        ("isBreakable", obj.is_breakable),
        ("isJumpingFountainWater", obj.is_jumping_fountain_water),
        ("isJumpingFountainSnow", obj.is_jumping_fountain_snow),
        ("isTelevision", obj.is_television),
        ("isAllowedOnQueue", obj.is_allowed_on_queue),
        ("isAllowedOnSlope", obj.is_allowed_on_slope),
    ):
        if val:
            properties[key] = True
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_path_addition_sprites(
    obj: PathAddition,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    normal = combine_model_world(obj.meshes, obj.model)
    broken = combine_model_world(obj.broken_meshes, obj.broken_model) if obj.broken_meshes else None
    full = combine_model_world(obj.full_meshes, obj.full_model) if obj.full_meshes else None
    images = render_path_addition(
        context,
        normal,
        broken,
        full,
        render_as=obj.render_as,
        breakable=obj.is_breakable,
        units_per_tile=obj.units_per_tile,
        progress=progress,
    )
    return write_images_dat_lgx(images, object_dir)


def export_path_addition_to(
    obj: PathAddition,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_path_addition_json(obj), _render_path_addition_sprites, skip_render, progress,
    )


def export_path_addition(
    obj: PathAddition, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_path_addition_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_path_addition_test(
    obj: PathAddition, context: Context, test_dir: Path | str = "test"
) -> None:
    """Render the path-addition sprites for fast iteration."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    normal = combine_model_world(obj.meshes, obj.model)
    broken = combine_model_world(obj.broken_meshes, obj.broken_model) if obj.broken_meshes else None
    full = combine_model_world(obj.full_meshes, obj.full_model) if obj.full_meshes else None
    images = render_path_addition(
        context, normal, broken, full,
        render_as=obj.render_as, breakable=obj.is_breakable, units_per_tile=obj.units_per_tile,
    )
    write_png(images[0], test_dir / "preview.png")
    for i, img in enumerate(images[1:], start=1):
        write_png(img, test_dir / f"item_{i}.png")
    write_png(combine_indexed_images(images), test_dir / "preview_combined.png")


def build_scenery_group_json(obj: SceneryGroup) -> dict[str, Any]:
    out = object_json_header(
        obj.id,
        object_type="scenery_group",
        original_id=obj.original_id,
        version=obj.version,
        authors=obj.authors,
    )
    out["properties"] = {"priority": obj.priority, "entries": list(obj.entries)}
    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_scenery_group_sprites(
    obj: SceneryGroup,
    context: Context,
    object_dir: Path,
    progress: ProgressFn | None = None,
) -> list[str]:
    """A scenery group has no geometry; emit the tab icon into both image slots
    (the engine's DrawPreview reads image+1). `context` is unused."""
    del context
    icon = obj.preview if obj.preview is not None else IndexedImage.blank(1, 1)
    if progress is not None:
        progress(1, 1)
    return write_images_dat_lgx([icon, icon], object_dir)


def export_scenery_group_to(
    obj: SceneryGroup,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
    progress: ProgressFn | None = None,
) -> None:
    _export_scenery(
        obj, context, parkobj_path, work_dir,
        build_scenery_group_json(obj), _render_scenery_group_sprites, skip_render, progress,
    )


def export_scenery_group(
    obj: SceneryGroup, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    export_scenery_group_to(
        obj,
        context,
        Path(output_directory) / f"{obj.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_scenery_group_test(
    obj: SceneryGroup, context: Context, test_dir: Path | str = "test"
) -> None:
    """Write the tab icon for fast iteration."""
    del context
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    icon = obj.preview if obj.preview is not None else IndexedImage.blank(1, 1)
    write_png(icon, test_dir / "icon.png")
    write_png(icon, test_dir / "preview_combined.png")
