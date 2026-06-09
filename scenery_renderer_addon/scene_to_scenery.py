"""
Read the Blender scene into the scenery generator's config + meshes.
"""

from __future__ import annotations

import math
import os
import tempfile

import bpy
from openrct2_object_common.blender.mesh_extract import (
    BASIS,
    SceneError,
    extract_mesh,
    material_base,
    object_position,
)
from openrct2_scenery_generator.constants import DOOR_SAMPLE_FRAMES, WALL_ANIMATION_FRAMES
from openrct2_scenery_generator.loader import build_scenery_group
from openrct2_x7_renderer.constants import MaterialFlag
from openrct2_x7_renderer.image import quantize_to_indexed
from openrct2_x7_renderer.mesh import Material, Mesh, load_texture
from openrct2_x7_renderer.types import IndexedImage

_REGION_MAP = {
    "NONE": (0, 0),
    "REMAP1": (MaterialFlag.IS_REMAPPABLE, 1),
    "REMAP2": (MaterialFlag.IS_REMAPPABLE, 2),
    "REMAP3": (MaterialFlag.IS_REMAPPABLE, 3),
    "GREYSCALE": (0, 4),
    "PEEP": (0, 5),
    "CHAIN": (0, 6),
}


def _material_from_bpy(bmat) -> Material:
    m, s = material_base(bmat, prop_attr="vgs_material", region_map=_REGION_MAP)
    if s is None:
        return m

    # Visible mask overrides regular mask
    if s.is_visible_mask:
        m.flags &= ~MaterialFlag.IS_MASK
        m.flags |= MaterialFlag.IS_VISIBLE_MASK
    if s.flat_shaded:
        m.flags |= MaterialFlag.IS_FLAT_SHADED

    # Wall-only classification.
    m.is_glass = bool(s.is_glass)
    if s.wall_side == "FRONT":
        m.is_front = True
    elif s.wall_side == "BACK":
        m.is_back = True

    if s.texture is not None:
        path = bpy.path.abspath(s.texture.filepath_from_user() or s.texture.filepath)
        if path and os.path.exists(path):
            m.texture = load_texture(path)
            m.flags |= MaterialFlag.HAS_TEXTURE
    return m


def _extract(obj, depsgraph) -> Mesh | None:
    return extract_mesh(obj, depsgraph, _material_from_bpy)


def _geometry_objects(scene) -> list:
    """Scene mesh objects that are part of the model (role != IGNORE)."""
    return [
        obj
        for obj in scene.objects
        if obj.type == "MESH" and obj.vgs_object.role != "IGNORE"
    ]


# Modifiers that animate an object's *vertices* (not just its transform) over
# the timeline
_DEFORM_MODIFIERS = {
    "ARMATURE",
    "MESH_DEFORM",
    "LATTICE",
    "HOOK",
    "CLOTH",
    "SOFT_BODY",
    "SURFACE_DEFORM",
    "CORRECTIVE_SMOOTH",
    "SIMPLE_DEFORM",
    "CAST",
    "CURVE",
    "WARP",
    "WAVE",
}


def _has_deforming_modifier(obj) -> bool:
    """True if obj's geometry changes across the timeline."""
    if any(m.type in _DEFORM_MODIFIERS for m in obj.modifiers):
        return True
    sk = getattr(obj.data, "shape_keys", None)
    return bool(sk and sk.animation_data)


def _make_deform_predicate(mode: str):
    """Return obj -> bool selecting per-pose mesh re-extraction."""
    if mode == "ALWAYS":
        return lambda obj: True
    if mode == "NEVER":
        return lambda obj: False
    return _has_deforming_modifier


def _frame_offsets(cycle: int, loop: str) -> tuple[list[int], int]:
    """Build the engine's `frameOffsets` table and the number of distinct poses
    to sample."""
    if loop == "PINGPONG":
        p = cycle // 2 + 1
        offsets = list(range(p)) + list(range(p - 2, 0, -1))
        return offsets, p
    return list(range(cycle)), cycle


def _sample_animation_poses(
    geo_objs, scene, num_poses: int, f_start: int, f_end: int, deforms=None
):
    """Sample every geometry object across num_poses evenly-spaced scene
    frames.

    Two per-object sampling modes, chosen by `deforms(obj)` (default: none):

    - **Rigid**: the mesh is extracted once at the rest frame, so pose 0 emits
      orientation [0, 0, 0] and later poses carry the rigid delta mapped into
      the renderer's OBJ-space YZX convention.
    - **Deforming**: the mesh is re-extracted at every pose (armature / shape
      keys / deform modifiers baked into the vertices by `_extract`, which
      also bakes that frame's world rotation+scale)
    """
    if deforms is None:
        deforms = lambda obj: False  # noqa: E731
    if f_end <= f_start:
        f_start, f_end = scene.frame_start, scene.frame_end
    if num_poses <= 1 or f_end <= f_start:
        frames = [f_start] * max(num_poses, 1)
    else:
        frames = [
            f_start + round(i * (f_end - f_start) / (num_poses - 1))
            for i in range(num_poses)
        ]

    # Each `frame_set` below forces a full-scene depsgraph re-evaluation on the
    # main thread, so this loop blocks the UI
    wm = getattr(bpy.context, "window_manager", None)
    win = getattr(bpy.context, "window", None)
    total = len(frames) + 1
    if wm is not None:
        wm.progress_begin(0, total)
    if win is not None:
        win.cursor_set("WAIT")

    orig_frame = scene.frame_current
    meshes: list[Mesh] = []
    poses: list[list[dict]] = [[] for _ in frames]
    try:
        # Rest pass: classify each object and pre-extract its rest mesh
        scene.frame_set(frames[0])
        dg = bpy.context.evaluated_depsgraph_get()
        rigid: list = []
        deforming: list = []
        for obj in geo_objs:
            mesh = _extract(obj, dg)
            if mesh is None:
                continue
            meshes.append(mesh)
            idx = len(meshes) - 1
            if deforms(obj):
                deforming.append((obj, idx))
            else:
                r_rest_inv = obj.evaluated_get(dg).matrix_world.to_3x3().inverted_safe()
                rigid.append((obj, idx, r_rest_inv))

        if wm is not None:
            wm.progress_update(1)

        last_slot = {obj: rest_idx for obj, rest_idx in deforming}
        for fi, f in enumerate(frames):
            scene.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            entries = poses[fi]
            for obj, idx, r_rest_inv in rigid:
                m_f = obj.evaluated_get(dg).matrix_world
                p = BASIS @ m_f.to_translation()
                r_rel = m_f.to_3x3() @ r_rest_inv
                r_obj = BASIS @ r_rel @ BASIS.transposed()
                # Renderer applies rotate_y(a) @ rotate_z(b) @ rotate_x(c), which
                # Blender's "YZX" Euler reconstructs as Ry(e.y) @ Rz(e.z) @ Rx(e.x).
                e = r_obj.to_euler("YZX")
                entries.append({
                    "mesh_index": idx,
                    "position": [float(p.x), float(p.y), float(p.z)],
                    "orientation": [
                        float(math.degrees(e.y)),
                        float(math.degrees(e.z)),
                        float(math.degrees(e.x)),
                    ],
                })
            for obj, rest_idx in deforming:
                if fi == 0:
                    slot = rest_idx
                else:
                    mesh = _extract(obj, dg)
                    if mesh is None:
                        slot = last_slot[obj]
                    else:
                        meshes.append(mesh)
                        slot = len(meshes) - 1
                        last_slot[obj] = slot
                entries.append({
                    "mesh_index": slot,
                    "position": object_position(obj),
                    "orientation": [0.0, 0.0, 0.0],
                })
            if wm is not None:
                wm.progress_update(fi + 2)
    finally:
        scene.frame_set(orig_frame)
        if wm is not None:
            wm.progress_end()
        if win is not None:
            win.cursor_set("DEFAULT")

    return meshes, poses




def build_config_and_meshes(context):
    """Return (config_dict, meshes) read from the active scene."""
    scene = context.scene
    ss = scene.vgs_scenery
    depsgraph = context.evaluated_depsgraph_get()

    geo_objs = _geometry_objects(scene)
    # A wall is a door OR animated, never both
    small_animated = ss.object_type == "scenery_small" and ss.is_animated
    wall_door = ss.object_type == "scenery_wall" and ss.is_door
    wall_animated = (
        ss.object_type == "scenery_wall" and ss.is_animated and not ss.is_door
    )

    meshes: list[Mesh] = []
    model: list[dict] = []
    animation: dict | None = None

    if small_animated:
        offsets, num_poses = _frame_offsets(int(ss.animation_cycle), ss.animation_loop)
        meshes, poses = _sample_animation_poses(
            geo_objs,
            scene,
            num_poses,
            int(ss.anim_start_frame),
            int(ss.anim_end_frame),
            _make_deform_predicate(ss.animation_deform),
        )
        animation = {
            "delay": int(ss.animation_delay),
            "mask": int(ss.animation_cycle) - 1,
            "num_frames": int(ss.animation_cycle),
            "frame_offsets": offsets,
            "frames": poses,
        }
    elif wall_door:
        # A door keyframes its leaf swinging open
        meshes, poses = _sample_animation_poses(
            geo_objs,
            scene,
            DOOR_SAMPLE_FRAMES,
            int(ss.anim_start_frame),
            int(ss.anim_end_frame),
            _make_deform_predicate(ss.animation_deform),
        )
        animation = {"frames": poses}
    elif wall_animated:
        # Animated walls cycle a fixed WALL_ANIMATION_FRAMES frames with no
        # delay/offset table
        meshes, poses = _sample_animation_poses(
            geo_objs,
            scene,
            WALL_ANIMATION_FRAMES,
            int(ss.anim_start_frame),
            int(ss.anim_end_frame),
            _make_deform_predicate(ss.animation_deform),
        )
        animation = {"frames": poses}
    else:
        for obj in geo_objs:
            mesh = _extract(obj, depsgraph)
            if mesh is None:
                continue
            idx = len(meshes)
            meshes.append(mesh)
            model.append({
                "mesh_index": idx,
                "position": object_position(obj),
                "orientation": [0, 0, 0],
            })

    if not meshes:
        raise SceneError(
            "No geometry found. Add a mesh and set its role to 'Geometry' "
            "in the OpenRCT2 Scenery panel."
        )

    authors = [a.strip() for a in ss.authors.split(",") if a.strip()]

    config: dict = {
        "object_type": ss.object_type,
        "id": ss.id,
        "name": ss.name,
        "authors": authors,
        "version": ss.version,
        "units_per_tile": float(ss.units_per_tile),
        "price": ss.price,
        "removal_price": ss.removal_price,
        "cursor": ss.cursor,
        "scenery_group": ss.scenery_group,
        "has_primary_colour": ss.has_primary_colour,
        "has_secondary_colour": ss.has_secondary_colour,
    }
    if animation is not None:
        config["animation"] = animation
    else:
        config["model"] = model

    if ss.object_type == "scenery_small":
        config.update({
            "height": int(ss.height),
            "shape": ss.shape,
            "is_rotatable": ss.is_rotatable,
            "is_stackable": ss.is_stackable,
            "requires_flat_surface": ss.requires_flat_surface,
            "prohibit_walls": ss.prohibit_walls,
            "is_tree": ss.is_tree,
        })
    elif ss.object_type == "scenery_wall":
        # A door takes the door paint path; otherwise isAnimated drives the
        # flat-only frame cycle
        wall_animation = ss.is_animated and not ss.is_door
        wall_cfg: dict = {
            "height": int(ss.wall_height),
            "has_tertiary_colour": ss.has_tertiary_colour,
            "is_allowed_on_slope": (not wall_animation) and ss.is_allowed_on_slope,
            "has_glass": (not wall_animation) and ss.has_glass,
            "is_double_sided": (not wall_animation) and ss.is_double_sided,
            "is_opaque": ss.is_opaque,
            "is_animated": wall_animation,
            "is_door": ss.is_door,
            "is_long_door_animation": ss.is_door and ss.is_long_door_animation,
        }
        if ss.is_door and ss.use_door_sound:
            wall_cfg["door_sound"] = int(ss.door_sound)
        config.update(wall_cfg)
    elif ss.object_type == "footpath_banner":
        config.update({"scrolling_mode": int(ss.scrolling_mode)})
    elif ss.object_type == "footpath_item":
        config.update({
            "render_as": ss.render_as,
            "is_breakable": ss.is_breakable,
            "is_television": ss.is_television,
            "is_jumping_fountain_water": ss.is_jumping_fountain_water,
            "is_jumping_fountain_snow": ss.is_jumping_fountain_snow,
            "is_allowed_on_queue": ss.is_allowed_on_queue,
            "is_allowed_on_slope": ss.is_allowed_on_slope,
        })
    else:
        if not ss.tiles:
            raise SceneError(
                "Large scenery needs at least one tile. Add one in the Tiles list."
            )
        config.update({
            "has_tertiary_colour": ss.has_tertiary_colour,
            "is_photogenic": ss.is_photogenic,
            "scrolling_mode": int(ss.scrolling_mode),
            "tiles": [_tile_config(t) for t in ss.tiles],
        })

    return config, meshes


def _bitmask(flags) -> int:
    """Pack a BoolVectorProperty of toggles into a bitmask (bit i = flags[i])."""
    return sum(1 << i for i, on in enumerate(flags) if on)


def _tile_config(t) -> dict:
    """One large-scenery tile config, including the per-tile supports flags and
    the packed corners/walls quadrant masks."""
    return {
        "x": int(t.x),
        "y": int(t.y),
        "z": int(t.z),
        "clearance": int(t.clearance),
        "has_supports": bool(t.has_supports),
        "allow_supports_above": bool(t.allow_supports_above),
        "corners": _bitmask(t.corners),
        "walls": _bitmask(t.walls),
    }


# Tab-icon edge size, in pixels
_GROUP_ICON_SIZE = 32


def _group_preview(ss):
    """Quantise the group's tab-icon image to the RCT2 palette, centered on its
    draw origin, or None when no icon is set."""
    if ss.icon is None:
        return None
    tmpdir = tempfile.mkdtemp(prefix="vgs_icon_")
    path = os.path.join(tmpdir, "icon.png")
    img = ss.icon.copy()
    try:
        img.file_format = "PNG"
        img.filepath_raw = path
        img.save()
        icon = quantize_to_indexed(path, size=_GROUP_ICON_SIZE)
    finally:
        bpy.data.images.remove(img)
    return IndexedImage(
        width=icon.width,
        height=icon.height,
        x_offset=-icon.width // 2,
        y_offset=-icon.height // 2,
        pixels=icon.pixels,
    )


def build_group(context):
    """Build a SceneryGroup (tab) from the scene settings."""
    ss = context.scene.vgs_scenery
    authors = [a.strip() for a in ss.authors.split(",") if a.strip()]
    entries = [e.object_id.strip() for e in ss.entries if e.object_id.strip()]
    config = {
        "object_type": "scenery_group",
        "id": ss.id,
        "name": ss.name,
        "authors": authors,
        "version": ss.version,
        "priority": int(ss.priority),
        "entries": entries,
    }
    return build_scenery_group(config, _group_preview(ss))
