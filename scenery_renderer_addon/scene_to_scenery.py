"""Read the Blender scene into the scenery generator's config + meshes.

The `bpy -> Mesh` adapter for scenery: instead of OBJ files, pull geometry
straight from scene objects and hand the core `build_small_scenery` /
`build_large_scenery` an in-memory config dict + `Mesh` list (same shape the
YAML loader produces).

Coordinate convention matches the renderer / vehicle add-on: OBJ space is
+X forward, +Y up, +Z right; a Blender vertex (bx, by, bz) maps to OBJ
(bx, bz, -by). 1 tile = TILE_SIZE OBJ units.
"""

from __future__ import annotations

import math
import os

import bpy
from openrct2_object_common.blender.mesh_extract import (
    BASIS,
    SceneError,
    extract_mesh,
    load_preview,
    material_base,
    object_position,
)
from openrct2_x7_renderer.constants import MaterialFlag
from openrct2_x7_renderer.mesh import Material, Mesh, load_texture

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

    # Visible mask overrides regular mask (mutually exclusive in the UI).
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
# the timeline. An object carrying one of these (or animated shape keys)
# must have its mesh re-extracted per pose to capture the deformation.
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
    """True if `obj`'s geometry (not merely its transform) changes across the
    timeline: it has a deform modifier (armature being the common case) or
    animated shape keys."""
    if any(m.type in _DEFORM_MODIFIERS for m in obj.modifiers):
        return True
    sk = getattr(obj.data, "shape_keys", None)
    return bool(sk and sk.animation_data)


def _make_deform_predicate(mode: str):
    """Return `obj -> bool` selecting per-pose mesh re-extraction. `mode` is the
    scene's `animation_deform`: ALWAYS bakes every object, NEVER bakes none, AUTO
    bakes only objects with deforming modifiers / animated shape keys."""
    if mode == "ALWAYS":
        return lambda obj: True
    if mode == "NEVER":
        return lambda obj: False
    return _has_deforming_modifier


def _frame_offsets(cycle: int, loop: str) -> tuple[list[int], int]:
    """Build the engine's `frameOffsets` table and the number of distinct poses
    to sample. The table length equals `cycle` (a power of two) so the engine's
    `(tick >> delay) & (cycle - 1)` index stays contiguous.

    LOOP: poses 0..cycle-1, table = identity.
    PINGPONG: poses 0..P-1 then back down, with P = cycle/2 + 1 so the forward+
    backward sweep is exactly `cycle` entries long."""
    if loop == "PINGPONG":
        p = cycle // 2 + 1
        offsets = list(range(p)) + list(range(p - 2, 0, -1))
        return offsets, p
    return list(range(cycle)), cycle


def _sample_animation_poses(
    geo_objs, scene, num_poses: int, f_start: int, f_end: int, deforms=None
):
    """Sample every geometry object across `num_poses` evenly-spaced scene
    frames. Returns ``(meshes, poses)`` where each pose is a list of model
    entries (one per kept object, same order every pose) and `meshes` is the
    shared pool the entries' `mesh_index` references.

    Two per-object sampling modes, chosen by `deforms(obj)` (default: none):

    - **Rigid** (mirrors the vehicle add-on's restraint sampler): the mesh is
      extracted once at the rest frame (baking the rest world rotation), so
      pose 0 emits orientation ``[0, 0, 0]`` and later poses carry the rigid
      delta mapped into the renderer's OBJ-space YZX convention. One pool mesh.
    - **Deforming**: the mesh is re-extracted at every pose (armature / shape
      keys / deform modifiers baked into the vertices by `_extract`, which
      also bakes that frame's world rotation+scale). The entry therefore carries
      identity orientation and only the translation. One pool mesh per pose.

    `scene.frame_current` is restored on exit."""
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
    # main thread, so this loop blocks the UI (worse with dense / deforming
    # meshes). Drive the cursor progress indicator so it reads as work, not a
    # hang. `total` = rest pass + one step per pose. Guarded for background
    # Blender, where there's no window / window manager.
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
        # Rest pass: classify each object and pre-extract its rest mesh. Rigid
        # objects keep this mesh for every pose; deforming objects reuse it for
        # pose 0 (same frame) and as the fallback if a later frame extracts empty.
        scene.frame_set(frames[0])
        dg = bpy.context.evaluated_depsgraph_get()
        rigid: list = []  # (obj, mesh_index, R_rest_inv)
        deforming: list = []  # (obj, rest_mesh_index)
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
                    slot = rest_idx  # rest mesh already in the pool
                else:
                    mesh = _extract(obj, dg)
                    if mesh is None:
                        slot = last_slot[obj]  # hold the last good geometry
                    else:
                        meshes.append(mesh)
                        slot = len(meshes) - 1
                        last_slot[obj] = slot
                # _extract baked this frame's world rotation+scale (and the
                # deformation) into the vertices; only the translation remains.
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
    """Return (config_dict, meshes, preview) read from the active scene.

    Raises SceneError with a user-facing message on invalid scenes.
    """
    scene = context.scene
    ss = scene.vgs_scenery
    depsgraph = context.evaluated_depsgraph_get()

    geo_objs = _geometry_objects(scene)
    animated = ss.object_type == "scenery_small" and ss.is_animated

    meshes: list[Mesh] = []
    model: list[dict] = []
    animation: dict | None = None

    if animated:
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
        config.update({
            "height": int(ss.wall_height),
            "has_tertiary_colour": ss.has_tertiary_colour,
            "is_allowed_on_slope": ss.is_allowed_on_slope,
            "has_glass": ss.has_glass,
            "is_double_sided": ss.is_double_sided,
        })
    else:  # scenery_large
        if not ss.tiles:
            raise SceneError(
                "Large scenery needs at least one tile. Add one in the Tiles list."
            )
        config.update({
            "has_tertiary_colour": ss.has_tertiary_colour,
            "is_photogenic": ss.is_photogenic,
            "scrolling_mode": int(ss.scrolling_mode),
            "tiles": [
                {"x": int(t.x), "y": int(t.y), "z": int(t.z), "clearance": int(t.clearance)}
                for t in ss.tiles
            ],
        })

    return config, meshes, load_preview(ss.preview)
