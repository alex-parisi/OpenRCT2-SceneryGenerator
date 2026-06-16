"""
Scenery sprite rendering.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from openrct2_object_common.sprite_render import (
    center_in_box,
    corner_anchors,
    render_corner_anchored_rotations,
    render_scene_view,
    render_scene_views,
    trim,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.geometry import (
    assign_faces_to_tiles,
    combine_model_world,
    subset_mesh,
)
from openrct2_x7_renderer.mesh import Mesh
from openrct2_x7_renderer.palette import TRANSPARENT_INDEX
from openrct2_x7_renderer.ray_trace import VIEWS, Context, FinalizedScene
from openrct2_x7_renderer.types import IndexedImage, Model

from .constants import DOOR_NUM_IMAGES, DOOR_SAMPLE_FRAMES, WALL_ANIMATION_FRAMES

# Single-model scene rendering and the tile's reference-corner anchor pattern
# are shared with every other object kind (see openrct2_object_common).
_render_scene_view = render_scene_view
_render_scene_views = render_scene_views

# OpenRCT2 anchors large-scenery sprites at the tile's reference CORNER (paint
# offset {0,0}), not its centre like small scenery ({15,15}).
_CORNER_BY_DIR = corner_anchors(TILE_SIZE)

# Reserved preview/menu image slots that precede the per-tile sprites.
# OpenRCT2 indexes per-tile sprites as base + 4 + sequence*4 + direction.
LARGE_SCENERY_PREVIEW_SLOTS = 4


# Animated small scenery reserves a leading group of 4 "base" sprites
ANIMATED_BASE_SLOTS = 4


def count_small_scenery_sprites(
    num_rotations: int, num_pose_groups: int = 1, *, animated: bool = False
) -> int:
    if animated:
        return ANIMATED_BASE_SLOTS + num_pose_groups * 4
    return num_rotations


def render_small_scenery(
    scene: FinalizedScene,
    num_rotations: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render the prepared scene under the first num_rotations cardinal views."""
    images = []
    for i in range(num_rotations):
        images.append(scene.render_view(VIEWS[i]))
        if progress is not None:
            progress(i + 1, num_rotations)
    return images


# Small-scenery paint anchors. The engine blits a full-tile sprite at the
# view-space point {15,15} (~tile centre); a half-tile ("2/4") sprite at {3,3};
# a VOFFSET_CENTRE sprite at {3,3}, or {1,1} when prohibitWalls is also set.
# Sprites for the non-centre anchors must be rendered against that anchor or
# they land up to 13 px away from their tile. Quarter-tile ("1/4") shapes take
# the engine's quadrant paint path instead, where VOFFSET_CENTRE only affects
# support heights, so they keep the default anchor.
def small_scenery_paint_anchor(
    shape: str, voffset_centre: bool, prohibit_walls: bool
) -> float | None:
    """The engine's paint-anchor coordinate (same on both axes) for a small
    scenery object, or None for the default tile-centre render path."""
    if shape.startswith("2/4"):
        return 3.0
    if voffset_centre and not shape.startswith("1/4"):
        return 1.0 if prohibit_walls else 3.0
    return None


def _anchor_corners(anchor: float, units_per_tile: float) -> list[tuple[float, float]]:
    """Per-direction OBJ-space (x, z) points that project onto the engine's
    view-space paint anchor (anchor, anchor); same rotation pattern as
    _CORNER_BY_DIR."""
    d = (anchor - 16.0) * units_per_tile / 32.0
    return [(-d, -d), (d, -d), (d, d), (-d, d)]


def render_small_scenery_anchored(
    context: Context,
    combined: Mesh,
    anchor: float,
    num_rotations: int = 4,
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render a small-scenery sprite set against a non-centre paint anchor."""
    if combined.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(num_rotations)]
    corners = _anchor_corners(anchor, units_per_tile)
    images = []
    for d in range(num_rotations):
        ox, oz = corners[d]
        translation = np.array([-ox, 0.0, -oz], dtype=np.float64)
        images.append(_render_scene_view(context, combined, translation, VIEWS[d]))
        if progress is not None:
            progress(d + 1, num_rotations)
    return images


def _render_mesh_rotations(
    context: Context,
    mesh: Mesh,
    anchor_corners: list[tuple[float, float]] | None = None,
) -> list[IndexedImage]:
    """Render a baked world-space mesh under all 4 cardinal rotations, anchored
    at the tile centre (or at per-direction anchor points). An empty mesh
    renders as four blank sprites."""
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(4)]
    if anchor_corners is None:
        return _render_scene_views(
            context, mesh, np.zeros(3, dtype=np.float64), [VIEWS[d] for d in range(4)]
        )
    return [
        _render_scene_view(
            context, mesh, np.array([-ox, 0.0, -oz], dtype=np.float64), VIEWS[d]
        )
        for d, (ox, oz) in enumerate(anchor_corners)
    ]


def _composite_over(base: IndexedImage, top: IndexedImage) -> IndexedImage:
    """Paint `top` over `base` (top wins where opaque), aligning the two by their
    draw offsets, and crop the result to its opaque bounds.

    Glues a per-frame moving submesh on top of the once-rendered static submesh
    so the static pixels stay byte-identical across every animation frame. This
    is a flat 2-D over-composite with no depth buffer, so it assumes the moving
    geometry paints in front of the static geometry (as a swinging lid or leaf
    does); where the static part should occlude the moving part the result is
    only approximate."""
    layers = [im for im in (base, top) if (im.pixels != TRANSPARENT_INDEX).any()]
    if not layers:
        return IndexedImage.blank(1, 1)
    left = min(im.x_offset for im in layers)
    top_edge = min(im.y_offset for im in layers)
    right = max(im.x_offset + im.width for im in layers)
    bottom = max(im.y_offset + im.height for im in layers)
    canvas = np.zeros((bottom - top_edge, right - left), dtype=np.uint8)
    for im in layers:  # base first, then top paints over it
        ys, xs = im.y_offset - top_edge, im.x_offset - left
        region = canvas[ys : ys + im.height, xs : xs + im.width]
        opaque = im.pixels != TRANSPARENT_INDEX
        region[opaque] = im.pixels[opaque]
    return trim(
        IndexedImage(
            width=right - left,
            height=bottom - top_edge,
            x_offset=left,
            y_offset=top_edge,
            pixels=canvas,
        )
    )


def render_small_scenery_animated(
    context: Context,
    meshes: list[Mesh],
    model: Model,
    num_pose_groups: int,
    progress: Callable[[int, int], None] | None = None,
    *,
    anchor: float | None = None,
    units_per_tile: float = TILE_SIZE,
) -> list[IndexedImage]:
    """Render an animated small-scenery sprite set in the engine's image order.

    When the per-frame meshes share frame 0's topology, the geometry is split
    into a static part (rendered once) and a moving part (rendered per frame),
    then composited, so the static pixels stay byte-identical across frames and
    only genuinely-moving geometry can change between them — this removes the
    dither/shading "swim" on the parts that hold still. Objects whose topology
    changes between frames fall back to rendering the whole mesh per frame."""
    corners = None if anchor is None else _anchor_corners(anchor, units_per_tile)
    frames = [combine_model_world(meshes, model, frame=g) for g in range(num_pose_groups)]

    if num_pose_groups > 1 and _stable_topology(frames):
        return _render_split_animated(context, frames, corners, progress)

    base = _render_mesh_rotations(context, frames[0], corners)
    if progress is not None:
        progress(1, num_pose_groups)
    images: list[IndexedImage] = list(base) + list(base)
    for g in range(1, num_pose_groups):
        images.extend(_render_mesh_rotations(context, frames[g], corners))
        if progress is not None:
            progress(g + 1, num_pose_groups)
    return images


def _render_split_animated(
    context: Context,
    frames: list[Mesh],
    corners: list[tuple[float, float]] | None,
    progress: Callable[[int, int], None] | None,
) -> list[IndexedImage]:
    """Render frames sharing one topology as a frozen static layer plus a
    per-frame moving layer (see :func:`render_small_scenery_animated`).

    Produces the engine's image order — 4 leading "base" sprites (pose 0)
    followed by 4 sprites per pose group — identical to the whole-mesh path."""
    moving = _moving_face_mask(frames)
    static_imgs = _render_mesh_rotations(context, _submesh(frames[0], ~moving), corners)
    groups: list[list[IndexedImage]] = []
    for g, frame_mesh in enumerate(frames):
        moving_imgs = _render_mesh_rotations(context, _submesh(frame_mesh, moving), corners)
        groups.append([_composite_over(static_imgs[d], moving_imgs[d]) for d in range(4)])
        if progress is not None:
            progress(g + 1, len(frames))
    images: list[IndexedImage] = list(groups[0])
    for group in groups:
        images.extend(group)
    return images


def count_large_scenery_sprites(num_tiles: int) -> int:
    """4 reserved preview images + one sprite per (tile, rotation)."""
    return LARGE_SCENERY_PREVIEW_SLOTS + 4 * num_tiles


# Walls. OpenRCT2 paints a wall with view-space direction d = (edge + rotation) & 3:
#   d=0 ("\", far edge,  paint anchor {0,0}):  flat image 1
#   d=1 ("/", near edge, paint anchor {1,31}): flat image 0 (+6 when double-sided)
#   d=2 ("\", near edge, paint anchor {31,0}): flat image 1 (+6 when double-sided)
#   d=3 ("/", far edge,  paint anchor {2,1}):  flat image 0
# A sprite's true content is the authored panel rendered under VIEWS[d]. The
# front images are shown unmodified at the far edges (d=0/3), so they render
# under views 0 and 3; a double-sided wall's back images are the truth for the
# near edges and render under views 1 and 2. (At the directions where the
# engine reuses a sprite the wall inherently appears end-mirrored, exactly as
# vanilla walls do.)
#
# The per-view translations reproduce vanilla sprite anchoring (verified
# against WALLBR32 / WALLJB16 / WALLBRDR .DAT offsets): every "/" sprite spans
# screen columns [-31, 1] from its anchor and every "\" sprite [-1, 31], with
# the wall plane one world unit inside the tile boundary.
# One land-height step as a vertical shear of the panel end, in OBJ Y.
_WALL_SLOPE_RISE = 1.34
_WALL_SLOPE_DOWN_RAISE = 1.2975


def _wall_view_translation(view: int, units_per_tile: float) -> NDArray[np.float64]:
    """OBJ-space translation anchoring the authored wall panel for `view`."""
    e = units_per_tile / 32.0  # one OpenRCT2 world unit
    half = units_per_tile / 2.0
    tx, tz = {
        0: (-e, -half),
        1: (0.0, -half + e),
        2: (e, half),
        3: (0.0, half - e),
    }[view]
    return np.array((tx, 0.0, tz), dtype=np.float64)


def _render_wall_view(
    context: Context, mesh: Mesh, view: int, units_per_tile: float
) -> IndexedImage:
    """Render the wall panel under one cardinal view, anchored for the engine's
    per-direction wall paint offsets."""
    return _render_scene_view(
        context, mesh, _wall_view_translation(view, units_per_tile), VIEWS[view]
    )


def _shear_wall(
    combined: Mesh,
    sign: float,
    rise: float = _WALL_SLOPE_RISE,
    y_raise: float = 0.0,
    units_per_tile: float = TILE_SIZE,
) -> Mesh:
    """Ramp the panel's Y along the tile edge (Z), raising the tile's +Z end by
    `sign * rise` so it follows a sloped edge. The ramp is a function of
    position across the tile span [-upt/2, +upt/2] (not the panel's own
    extent), so a panel shorter than the tile edge rises only by its share of
    the slope."""
    v = combined.vertices.astype(np.float64).copy()
    t = v[:, 2] / units_per_tile + 0.5
    v[:, 1] += sign * rise * t + y_raise
    return Mesh(
        vertices=v.astype(np.float32),
        normals=combined.normals,
        uvs=combined.uvs,
        faces=combined.faces,
        face_materials=combined.face_materials,
        materials=combined.materials,
    )




def _submesh(mesh: Mesh, keep: NDArray[np.bool_]) -> Mesh:
    """A mesh with only the faces selected by the boolean keep mask."""
    return Mesh(
        vertices=mesh.vertices,
        normals=mesh.normals,
        uvs=mesh.uvs,
        faces=mesh.faces[keep],
        face_materials=mesh.face_materials[keep],
        materials=mesh.materials,
    )


# A vertex that shifts by more than this (OBJ units) between frames counts as
# part of the moving geometry (a swinging leaf, lid, ...).
_MOTION_EPS = 1e-4


def _stable_topology(frames: list[Mesh]) -> bool:
    """True if every frame shares frame 0's vertex- and face-array shapes, so a
    per-face moving/static split computed against frame 0 applies to all frames."""
    return all(
        m.vertices.shape == frames[0].vertices.shape
        and m.faces.shape == frames[0].faces.shape
        for m in frames[1:]
    )


def _moving_face_mask(frames: list[Mesh]) -> NDArray[np.bool_]:
    """Classify each face of frame 0 as moving (True) or static (False) by whether
    any of its vertices shift by more than ``_MOTION_EPS`` across ``frames``.

    Requires :func:`_stable_topology`. If nothing moves, every face is reported
    as moving so callers need not special-case a wholly static object."""
    base = frames[0]
    moved_vertex = np.zeros(base.vertices.shape[0], dtype=bool)
    for m in frames[1:]:
        moved_vertex |= np.abs(base.vertices - m.vertices).max(axis=1) > _MOTION_EPS
    moved_face = np.asarray(moved_vertex[base.faces].any(axis=1), dtype=np.bool_)
    if not moved_face.any():
        return np.ones(base.faces.shape[0], dtype=bool)
    return moved_face


def _filter_glass(mesh: Mesh, want_glass: bool) -> Mesh:
    """Sub-mesh of the faces whose material's is_glass matches want_glass."""
    by_material = np.array(
        [m.is_glass == want_glass for m in mesh.materials], dtype=bool
    )
    return _submesh(mesh, by_material[mesh.face_materials])


def _filter_keep(mesh: Mesh, attr: str) -> Mesh:
    """Sub-mesh of the faces whose material has attr set."""
    by_material = np.array([getattr(m, attr) for m in mesh.materials], dtype=bool)
    return _submesh(mesh, by_material[mesh.face_materials])


def _filter_side(mesh: Mesh, *, drop_attr: str) -> Mesh:
    """Sub-mesh excluding faces whose material has drop_attr set."""
    by_material = np.array(
        [not getattr(m, drop_attr) for m in mesh.materials], dtype=bool
    )
    return _submesh(mesh, by_material[mesh.face_materials])


# The two paint views of a block: ("/" view, "\" view)
_WALL_FRONT_VIEWS = (3, 0)
_WALL_BACK_VIEWS = (1, 2)


def _render_wall_block(
    context: Context,
    mesh: Mesh,
    slope: bool,
    *,
    views: tuple[int, int],
    units_per_tile: float = TILE_SIZE,
    rise: float = _WALL_SLOPE_RISE,
    down_raise: float = _WALL_SLOPE_DOWN_RAISE,
) -> list[IndexedImage]:
    """One wall image block rendered under its two paint views `views` =
    ("/" view, "\\" view): (3, 0) for front and glass blocks, (1, 2) for a
    double-sided wall's back block.

    Block offsets 0/1 are the flat sprites. With `slope`, offsets 2-5 follow
    the engine's table — image 2 = (d1, slope 2) / (d3, slope 1), image 3 =
    (d0, slope 2) / (d2, slope 1), images 4/5 the opposite slopes — which makes
    the sheared end alternate between the two views and flip between the front
    and back blocks."""
    va, vb = views
    n = 6 if slope else 2
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(n)]

    def render(m: Mesh, view: int) -> IndexedImage:
        return _render_wall_view(context, m, view, units_per_tile)

    images = [render(mesh, va), render(mesh, vb)]
    if slope:
        up = _shear_wall(mesh, +1.0, rise, units_per_tile=units_per_tile)
        down = _shear_wall(mesh, -1.0, rise, y_raise=down_raise, units_per_tile=units_per_tile)
        if views == _WALL_FRONT_VIEWS:
            images += [render(down, va), render(up, vb), render(up, va), render(down, vb)]
        else:
            images += [render(up, va), render(down, vb), render(down, va), render(up, vb)]
    return images


def render_wall(
    context: Context,
    combined: Mesh,
    allowed_on_slope: bool,
    has_glass: bool = False,
    is_double_sided: bool = False,
    units_per_tile: float = TILE_SIZE,
) -> list[IndexedImage]:
    """Render a wall sprite set."""
    s = units_per_tile / TILE_SIZE
    anchors: dict[str, Any] = {
        "units_per_tile": units_per_tile,
        "rise": _WALL_SLOPE_RISE * s,
        "down_raise": _WALL_SLOPE_DOWN_RAISE * s,
    }
    if has_glass:
        body = _filter_glass(combined, want_glass=False)
        glass = _filter_glass(combined, want_glass=True)
        return _render_wall_block(
            context, body, slope=True, views=_WALL_FRONT_VIEWS, **anchors
        ) + _render_wall_block(context, glass, slope=True, views=_WALL_FRONT_VIEWS, **anchors)
    if is_double_sided:
        front = _filter_side(combined, drop_attr="is_back")
        back = _filter_side(combined, drop_attr="is_front")
        return _render_wall_block(
            context, front, slope=True, views=_WALL_FRONT_VIEWS, **anchors
        ) + _render_wall_block(context, back, slope=True, views=_WALL_BACK_VIEWS, **anchors)
    return _render_wall_block(
        context, combined, slope=allowed_on_slope, views=_WALL_FRONT_VIEWS, **anchors
    )


def count_wall_sprites(
    *, is_animated: bool = False, allowed_on_slope: bool = False,
    has_glass: bool = False, is_double_sided: bool = False,
) -> int:
    """Image count for a wall sprite set."""
    if is_animated:
        return WALL_ANIMATION_FRAMES * 2
    if has_glass or is_double_sided:
        return 12
    return 6 if allowed_on_slope else 2


def render_wall_animated(
    context: Context,
    meshes: list[Mesh],
    model: Model,
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render an animated wall sprite set in the engine's image order."""
    images: list[IndexedImage] = []
    for f in range(WALL_ANIMATION_FRAMES):
        combined = combine_model_world(meshes, model, frame=f)
        if combined.faces.shape[0] == 0:
            images += [IndexedImage.blank(1, 1), IndexedImage.blank(1, 1)]
        else:
            images += [
                _render_wall_view(context, combined, 3, units_per_tile),
                _render_wall_view(context, combined, 0, units_per_tile),
            ]
        if progress is not None:
            progress(f + 1, WALL_ANIMATION_FRAMES)
    return images


def count_wall_door_sprites() -> int:
    """A door wall always has the engine's fixed 36-image table."""
    return DOOR_NUM_IMAGES


def _door_leaf_face_mask(closed: Mesh, opened: Mesh) -> NDArray[np.bool_]:
    """Classify each face as part of the swinging leaf (True) or the static frame
    (False) by whether any of its vertices move between the closed and open pose."""
    return _moving_face_mask([closed, opened])


def render_wall_door(
    context: Context,
    meshes: list[Mesh],
    model: Model,
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render a door-wall sprite set in the engine's image order.

    The fixed 36-image table is 9 groups of (leaf "/", frame "/", leaf "\\",
    frame "\\"). Group 0 is the closed pose — shared by both edge pairs, so it
    renders under the far-edge views like a plain wall. Groups 1-4 are the
    swing poses for the near edges (views 1 and 2) and groups 5-8 the same
    poses for the far edges (views 3 and 0), which is where the engine's
    "mirrored swing" images come from."""
    blank = IndexedImage.blank(1, 1)

    def render(mesh: Mesh, view: int) -> IndexedImage:
        if mesh.faces.shape[0] == 0:
            return blank
        return _render_wall_view(context, mesh, view, units_per_tile)

    sampled = [
        combine_model_world(meshes, model, frame=f) for f in range(DOOR_SAMPLE_FRAMES)
    ]
    if _stable_topology(sampled):
        leaf_mask = _door_leaf_face_mask(sampled[0], sampled[-1])
        frame_mesh = _submesh(sampled[0], ~leaf_mask)
        closed_leaf = _submesh(sampled[0], leaf_mask)
        swing_leaves = [_submesh(m, leaf_mask) for m in sampled[1:DOOR_SAMPLE_FRAMES]]
    else:
        # Topology changes between poses (per-pose re-extracted deforming
        # meshes), so the vertex-motion leaf/frame split is undefined: treat
        # each whole pose as the swinging leaf with an empty static frame.
        frame_mesh = _submesh(sampled[0], np.zeros(sampled[0].faces.shape[0], dtype=bool))
        closed_leaf = sampled[0]
        swing_leaves = sampled[1:DOOR_SAMPLE_FRAMES]

    frame_imgs = {view: render(frame_mesh, view) for view in range(4)}

    groups: list[tuple[Mesh, int, int]] = [(closed_leaf, *_WALL_FRONT_VIEWS)]
    groups += [(leaf, *_WALL_BACK_VIEWS) for leaf in swing_leaves]
    groups += [(leaf, *_WALL_FRONT_VIEWS) for leaf in swing_leaves]

    images: list[IndexedImage] = []
    for gi, (leaf, va, vb) in enumerate(groups):
        images += [render(leaf, va), frame_imgs[va], render(leaf, vb), frame_imgs[vb]]
        if progress is not None:
            progress(gi + 1, len(groups))
    return images


# Per-direction half-tile corner offsets, scaled to the authored render scale;
# shared with every other object kind (see openrct2_object_common).
_corners_by_dir = corner_anchors


def _render_4_rotations(
    context: Context,
    mesh: Mesh,
    cx: float,
    cz: float,
    corners: list[tuple[float, float]] | None = None,
) -> list[IndexedImage]:
    """Render the 4 cardinal rotations of `mesh`, anchoring each direction's
    world origin at the tile's per-direction corner. The corner-anchor pattern
    (and the single-scene fast path when all corners are equal) is the shared
    primitive (see openrct2_object_common)."""
    return render_corner_anchored_rotations(
        context,
        mesh,
        center=(cx, cz),
        corners=corners if corners is not None else _CORNER_BY_DIR,
    )


def render_large_scenery(
    context: Context,
    combined: Mesh,
    tile_centers_xz: NDArray[np.float64],
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render a large-scenery sprite set in OpenRCT2 image order."""
    images: list[IndexedImage] = []
    corners = _corners_by_dir(units_per_tile)
    num_tiles = tile_centers_xz.shape[0]
    total = 1 + num_tiles

    anchor = (
        tile_centers_xz.mean(axis=0) if num_tiles else np.zeros(2, dtype=np.float64)
    )
    images.extend(
        _render_4_rotations(context, combined, float(anchor[0]), float(anchor[1]), corners)
    )
    if progress is not None:
        progress(1, total)

    # Per-tile sprites, anchored at each tile's per-direction corner.
    assign = assign_faces_to_tiles(combined, tile_centers_xz)
    for seq in range(num_tiles):
        sub = subset_mesh(combined, assign == seq)
        cx, cz = tile_centers_xz[seq]
        images.extend(_render_4_rotations(context, sub, float(cx), float(cz), corners))
        if progress is not None:
            progress(seq + 2, total)
    return images


# Per-direction banner placement, as (OBJ X, OBJ Z) fractions of one tile.
_BANNER_TRANSLATION_FRAC = [
    (-0.030, -0.470),
    (0.970, -0.470),
    (0.970, 0.470),
    (-0.030, 0.470),
]


def render_banner(
    context: Context,
    combined: Mesh,
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render a banner sprite set in OpenRCT2 image order."""
    back = _filter_keep(combined, "is_back")
    front = _filter_side(combined, drop_attr="is_back")
    images: list[IndexedImage] = []
    for d in range(4):
        fx, fz = _BANNER_TRANSLATION_FRAC[d]
        t = np.array([fx * units_per_tile, 0.0, fz * units_per_tile], dtype=np.float64)
        for layer in (back, front):
            if layer.faces.shape[0] == 0:
                images.append(IndexedImage.blank(1, 1))
            else:
                images.append(_render_scene_view(context, layer, t, VIEWS[d]))
        if progress is not None:
            progress(d + 1, 4)
    return images


# Path additions
_PATH_ADDITION_CORNERS = [(0.0, 0.0)] * 4

# Scenery-window button geometry
_SCENERY_BUTTON_W = 66
_SCENERY_BUTTON_H = 80
_PATH_ADDITION_PREVIEW_DRAW = (11, 16)


def _center_in_button(img: IndexedImage, draw: tuple[int, int]) -> IndexedImage:
    """Re-anchor a preview sprite so its content centers in the scenery-window
    button when the window blits it at the fixed `draw` position."""
    return center_in_box(img, _SCENERY_BUTTON_W, _SCENERY_BUTTON_H, draw=draw)


def count_path_addition_sprites(render_as: str, *, breakable: bool) -> int:
    """1 menu preview + 4 edge sprites, plus a 4-sprite broken block (bins always,
    lamps/benches when breakable) and a 4-sprite full block (bins only)."""
    n = 1 + 4
    if render_as == "bin":
        return n + 4 + 4
    if breakable and render_as in ("lamp", "bench"):
        n += 4
    return n


def render_path_addition(
    context: Context,
    normal: Mesh,
    broken: Mesh | None,
    full: Mesh | None,
    *,
    render_as: str,
    breakable: bool,
    units_per_tile: float = TILE_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render a path-addition sprite set in OpenRCT2 image order."""
    del units_per_tile

    def edge_sprites(mesh: Mesh) -> list[IndexedImage]:
        return _render_4_rotations(context, mesh, 0.0, 0.0, _PATH_ADDITION_CORNERS)

    normal_edges = edge_sprites(normal)
    if normal.faces.shape[0] == 0:
        images = [IndexedImage.blank(1, 1)]
    else:
        # The menu preview is the direction-0 edge render, re-anchored to
        # centre in the scenery-window button.
        images = [_center_in_button(normal_edges[0], _PATH_ADDITION_PREVIEW_DRAW)]
    images.extend(normal_edges)
    if progress is not None:
        progress(1, 3)

    if render_as == "bin" or (breakable and render_as in ("lamp", "bench")):
        images.extend(edge_sprites(broken) if broken is not None else list(normal_edges))
    if progress is not None:
        progress(2, 3)

    if render_as == "bin":
        images.extend(edge_sprites(full) if full is not None else list(normal_edges))
    if progress is not None:
        progress(3, 3)
    return images
