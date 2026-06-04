"""
Build object.json and assemble the scenery .parkobj ZIP.
"""

import json
import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from openrct2_x7_renderer.geometry import combine_model_world
from openrct2_x7_renderer.image import write_png
from openrct2_x7_renderer.images_dat import write_images_dat
from openrct2_x7_renderer.ray_trace import VIEWS, Context, render_view, rotate_x, rotate_y, rotate_z

from .constants import COORDS_PER_TILE, SCROLLING_MODE_NONE
from .sprite_renderer import (
    render_large_scenery,
    render_small_scenery,
    render_small_scenery_animated,
    render_wall,
)
from .types import LargeScenery, SmallScenery, WallScenery


def _add_model_to_context(
    obj: SmallScenery | WallScenery, context: Context, frame: int = 0
) -> None:
    """Add the scenery's placed meshes to the open scene at the given pose
    frame (default 0 = the static/first pose)."""
    for mesh_frames in obj.model.meshes:
        mf = mesh_frames[min(frame, len(mesh_frames) - 1)]
        if mf.mesh_index == -1:
            continue
        rx, ry, rz = mf.orientation * math.pi / 180.0
        matrix = rotate_y(rx) @ rotate_z(ry) @ rotate_x(rz)
        translation = mf.position.astype(np.float64)
        context.add_model(obj.meshes[mf.mesh_index], matrix, translation, 0)


def build_small_scenery_json(obj: SmallScenery) -> dict[str, Any]:
    out: dict[str, Any] = {"id": obj.id}
    if obj.original_id:
        out["originalId"] = obj.original_id
    out["version"] = obj.version
    out["authors"] = list(obj.authors)
    out["objectType"] = "scenery_small"

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
    }
    if obj.is_animated:
        properties["isAnimated"] = True
        properties["animationDelay"] = obj.animation_delay
        properties["animationMask"] = obj.animation_mask
        properties["numFrames"] = obj.num_frames
        properties["frameOffsets"] = list(obj.frame_offsets)
        # Required so the engine skips the always-on static base-parent draw
        # (Paint.SmallScenery.cpp:193) that would otherwise overlay a frozen
        # pose-0 ghost on the animation; it also shifts the animation image
        # index +4 past the base group we emit (line 294). Vanilla animated
        # scenery (e.g. rct2tt.scenery_small.gangster) sets the same flag.
        properties["SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED"] = True
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_sprites(obj: SmallScenery, context: Context, object_dir: Path) -> list[str]:
    if obj.is_animated:
        images = render_small_scenery_animated(
            context, obj.meshes, obj.model, obj.num_pose_groups
        )
    else:
        context.begin_render()
        _add_model_to_context(obj, context)
        context.finalize_render()
        images = render_small_scenery(context, num_rotations=obj.num_rotations)
        context.end_render()

    out_path = object_dir / "images.dat"
    write_images_dat(images, out_path)
    print(f"wrote {out_path} ({len(images)} sprites, {out_path.stat().st_size / 1024:.1f} KB)")
    return [f"$LGX:images.dat[0..{len(images) - 1}]"]


def _make_parkobj(object_dir: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(object_dir / "object.json", "object.json")
        zf.write(object_dir / "images.dat", "images.dat")


def export_small_scenery_to(
    obj: SmallScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
) -> None:
    parkobj_path = Path(parkobj_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    obj_json = build_small_scenery_json(obj)

    if skip_render:
        prev = json.loads((work_dir / "object.json").read_text())
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError('Property "images" is not an array')
    else:
        for p in (work_dir / "object.json", work_dir / "images.dat"):
            p.unlink(missing_ok=True)
        images_json = _render_sprites(obj, context, work_dir)

    obj_json["images"] = images_json
    (work_dir / "object.json").write_text(json.dumps(obj_json, indent=4))

    parkobj_path.parent.mkdir(parents=True, exist_ok=True)
    _make_parkobj(work_dir, parkobj_path)


def export_small_scenery(
    obj: SmallScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    output_directory = Path(output_directory)
    export_small_scenery_to(
        obj,
        context,
        output_directory / f"{obj.id}.parkobj",
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
    if obj.is_animated:
        images = render_small_scenery_animated(
            context, obj.meshes, obj.model, obj.num_pose_groups
        )
        for d in range(4):
            write_png(images[d], test_dir / f"base_{d}.png")
        for g in range(obj.num_pose_groups):
            for d in range(4):
                write_png(images[4 + g * 4 + d], test_dir / f"pose{g}_{d}.png")
        return
    context.begin_render()
    _add_model_to_context(obj, context)
    context.finalize_render()
    for i in range(obj.num_rotations):
        img = render_view(context, VIEWS[i])
        write_png(img, test_dir / f"scenery_{i}.png")
    context.end_render()


# ---------------------------------------------------------------------------
# Large scenery
# ---------------------------------------------------------------------------


def _tile_centers_xz(obj: LargeScenery) -> np.ndarray:
    """Tile centres in OBJ horizontal (X, Z) units (1 tile = units_per_tile
    units). OpenRCT2 tile x -> OBJ X, tile y -> OBJ Z."""
    if not obj.tiles:
        return np.zeros((0, 2), dtype=np.float64)
    upt = obj.units_per_tile
    return np.array([[t.x * upt, t.y * upt] for t in obj.tiles], dtype=np.float64)


def build_large_scenery_json(obj: LargeScenery) -> dict[str, Any]:
    out: dict[str, Any] = {"id": obj.id}
    if obj.original_id:
        out["originalId"] = obj.original_id
    out["version"] = obj.version
    out["authors"] = list(obj.authors)
    out["objectType"] = "scenery_large"

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
                # Config x/y are tile indices; OpenRCT2 stores them in
                # coordinate units (COORDS_PER_TILE per tile). The sign is
                # negated: the renderer projects OBJ +X/+Z to the upper-right,
                # while OpenRCT2 places map +x/+y toward the lower-left
                # (screen = (y-x, (x+y)/2 - z)). Negating keeps the in-game
                # footprint aligned with the rendered geometry. z/clearance are
                # already in coordinate units.
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
    # Only emit scrollingMode for actual scrolling signs; otherwise omit it so
    # OpenRCT2 defaults to "none" (255). Emitting 0 paints garbage text.
    if obj.scrolling_mode != SCROLLING_MODE_NONE:
        properties["scrollingMode"] = obj.scrolling_mode
    if obj.scenery_group:
        properties["sceneryGroup"] = obj.scenery_group
    out["properties"] = properties

    out["strings"] = {"name": {"en-GB": obj.name}}
    return out


def _render_large_sprites(obj: LargeScenery, context: Context, object_dir: Path) -> list[str]:
    combined = combine_model_world(obj.meshes, obj.model)
    centers = _tile_centers_xz(obj)
    images = render_large_scenery(context, combined, centers, obj.units_per_tile)
    out_path = object_dir / "images.dat"
    write_images_dat(images, out_path)
    print(
        f"wrote {out_path} ({len(images)} sprites for {obj.num_tiles} tiles, "
        f"{out_path.stat().st_size / 1024:.1f} KB)"
    )
    return [f"$LGX:images.dat[0..{len(images) - 1}]"]


def export_large_scenery_to(
    obj: LargeScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
) -> None:
    parkobj_path = Path(parkobj_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    obj_json = build_large_scenery_json(obj)

    if skip_render:
        prev = json.loads((work_dir / "object.json").read_text())
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError('Property "images" is not an array')
    else:
        for p in (work_dir / "object.json", work_dir / "images.dat"):
            p.unlink(missing_ok=True)
        images_json = _render_large_sprites(obj, context, work_dir)

    obj_json["images"] = images_json
    (work_dir / "object.json").write_text(json.dumps(obj_json, indent=4))

    parkobj_path.parent.mkdir(parents=True, exist_ok=True)
    _make_parkobj(work_dir, parkobj_path)


def export_large_scenery(
    obj: LargeScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    output_directory = Path(output_directory)
    export_large_scenery_to(
        obj,
        context,
        output_directory / f"{obj.id}.parkobj",
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
    # images[0..3] preview, then 4 per tile.
    for d in range(4):
        write_png(images[d], test_dir / f"preview_{d}.png")
    for seq in range(obj.num_tiles):
        for d in range(4):
            write_png(images[4 + seq * 4 + d], test_dir / f"tile{seq}_{d}.png")


# ---------------------------------------------------------------------------
# Walls (scenery_wall)
# ---------------------------------------------------------------------------


def build_wall_scenery_json(obj: WallScenery) -> dict[str, Any]:
    out: dict[str, Any] = {"id": obj.id}
    if obj.original_id:
        out["originalId"] = obj.original_id
    out["version"] = obj.version
    out["authors"] = list(obj.authors)
    out["objectType"] = "scenery_wall"

    properties: dict[str, Any] = {
        "price": obj.price,
        "cursor": obj.cursor,
        "height": obj.height,
    }
    # The glass x double-sided `+12` combo uses a separate, asymmetric layout we
    # don't generate (Paint.Wall.cpp:229-231). Emitting both flags would make the
    # engine index past our 12 images into nothing (silent glitch, same failure
    # class as the vehicle-animation gotcha). Keep glass (vanilla-common), drop
    # double-sided.
    double_sided = obj.is_double_sided
    if double_sided and obj.has_glass:
        print("warning: glass + isDoubleSided combo is unsupported; ignoring isDoubleSided")
        double_sided = False

    # Emit only the flags that are set (OpenRCT2 treats absent as false; for the
    # inverted isAllowedOnSlope, absent => can't build on slope).
    for key, val in (
        ("hasPrimaryColour", obj.has_primary_colour),
        ("hasSecondaryColour", obj.has_secondary_colour),
        ("hasTertiaryColour", obj.has_tertiary_colour),
        ("isAllowedOnSlope", obj.is_allowed_on_slope),
        ("hasGlass", obj.has_glass),
        ("isDoubleSided", double_sided),
        ("isDoor", obj.is_door),
        ("isLongDoorAnimation", obj.is_long_door_animation),
        ("isAnimated", obj.is_animated),
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


def _render_wall_sprites(obj: WallScenery, context: Context, object_dir: Path) -> list[str]:
    # Flat (2) + slope (4 more); +6 for the glass overlay or the double-sided
    # back block.
    combined = combine_model_world(obj.meshes, obj.model)
    images = render_wall(
        context,
        combined,
        obj.is_allowed_on_slope,
        obj.has_glass,
        obj.is_double_sided,
        obj.units_per_tile,
    )

    out_path = object_dir / "images.dat"
    write_images_dat(images, out_path)
    print(f"wrote {out_path} ({len(images)} sprites, {out_path.stat().st_size / 1024:.1f} KB)")
    return [f"$LGX:images.dat[0..{len(images) - 1}]"]


def export_wall_scenery_to(
    obj: WallScenery,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
) -> None:
    parkobj_path = Path(parkobj_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    obj_json = build_wall_scenery_json(obj)

    if skip_render:
        prev = json.loads((work_dir / "object.json").read_text())
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError('Property "images" is not an array')
    else:
        for p in (work_dir / "object.json", work_dir / "images.dat"):
            p.unlink(missing_ok=True)
        images_json = _render_wall_sprites(obj, context, work_dir)

    obj_json["images"] = images_json
    (work_dir / "object.json").write_text(json.dumps(obj_json, indent=4))

    parkobj_path.parent.mkdir(parents=True, exist_ok=True)
    _make_parkobj(work_dir, parkobj_path)


def export_wall_scenery(
    obj: WallScenery, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    output_directory = Path(output_directory)
    export_wall_scenery_to(
        obj,
        context,
        output_directory / f"{obj.id}.parkobj",
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
