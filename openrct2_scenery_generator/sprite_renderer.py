"""
Scenery sprite rendering.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.geometry import (
    assign_faces_to_tiles,
    combine_model_world,
    split_mesh_by_ghost,
    subset_mesh,
)
from openrct2_x7_renderer.mesh import Mesh
from openrct2_x7_renderer.ray_trace import VIEWS, Context, FinalizedScene, SceneBuilder
from openrct2_x7_renderer.types import IndexedImage, Model

from .constants import DOOR_NUM_IMAGES, DOOR_SAMPLE_FRAMES, WALL_ANIMATION_FRAMES

_IDENTITY3 = np.eye(3, dtype=np.float64)


def _add_split_ghost(scene: SceneBuilder, mesh: Mesh, translation: NDArray[np.float64]) -> None:
    """Add `mesh` to `scene`, splitting ghost faces into their own GHOST model so
    the renderer traces through them (e.g. baked-in ghost geometry)."""
    for sub_mesh, mask in split_mesh_by_ghost(mesh):
        scene.add_model(sub_mesh, _IDENTITY3, translation, mask)


def _render_scene_view(
    context: Context, mesh: Mesh, translation: NDArray[np.float64], view: NDArray[np.float64]
) -> IndexedImage:
    """Render a single model under a single view in its own scene."""
    with context.begin_render() as scene:
        _add_split_ghost(scene, mesh, translation)
        with scene.finalize() as ready:
            return ready.render_view(view)


def _render_scene_views(
    context: Context, mesh: Mesh, translation: NDArray[np.float64], views: list[NDArray[np.float64]]
) -> list[IndexedImage]:
    """Render a single model under several views, sharing one finalized scene."""
    with context.begin_render() as scene:
        _add_split_ghost(scene, mesh, translation)
        with scene.finalize() as ready:
            return [ready.render_view(v) for v in views]

# OpenRCT2 anchors large-scenery sprites at the tile's reference CORNER (paint
# offset {0,0}), not its centre like small scenery ({15,15})
_HALF_TILE = TILE_SIZE / 2.0
_CORNER_BY_DIR = [
    (_HALF_TILE, _HALF_TILE),
    (-_HALF_TILE, _HALF_TILE),
    (-_HALF_TILE, -_HALF_TILE),
    (_HALF_TILE, -_HALF_TILE),
]

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
# they land up to 13 px away from their tile.
def small_scenery_paint_anchor(
    shape: str, voffset_centre: bool, prohibit_walls: bool
) -> float | None:
    """The engine's paint-anchor coordinate (same on both axes) for a small
    scenery object, or None for the default tile-centre render path."""
    if shape.startswith("2/4"):
        return 3.0
    if voffset_centre:
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


def _render_pose_rotations(
    context: Context,
    meshes: list[Mesh],
    model: Model,
    frame: int,
    anchor_corners: list[tuple[float, float]] | None = None,
) -> list[IndexedImage]:
    """Bake pose frame's placements and render all 4 cardinal rotations,
    anchored at the tile center (or at per-direction anchor points)."""
    combined = combine_model_world(meshes, model, frame=frame)
    if anchor_corners is None:
        return _render_scene_views(
            context, combined, np.zeros(3, dtype=np.float64), [VIEWS[d] for d in range(4)]
        )
    return [
        _render_scene_view(
            context, combined, np.array([-ox, 0.0, -oz], dtype=np.float64), VIEWS[d]
        )
        for d, (ox, oz) in enumerate(anchor_corners)
    ]


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
    """Render an animated small-scenery sprite set in the engine's image order"""
    corners = None if anchor is None else _anchor_corners(anchor, units_per_tile)
    base = _render_pose_rotations(context, meshes, model, 0, corners)
    if progress is not None:
        progress(1, num_pose_groups)
    images: list[IndexedImage] = list(base) + list(base)
    for g in range(1, num_pose_groups):
        images.extend(_render_pose_rotations(context, meshes, model, g, corners))
        if progress is not None:
            progress(g + 1, num_pose_groups)
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


def _filter_glass(mesh: Mesh, want_glass: bool) -> Mesh:
    """Sub-mesh of the faces whose material's is_glass matches want_glass."""
    keep = np.array(
        [mesh.materials[m].is_glass == want_glass for m in mesh.face_materials],
        dtype=bool,
    )
    return _submesh(mesh, keep)


def _filter_keep(mesh: Mesh, attr: str) -> Mesh:
    """Sub-mesh of the faces whose material has attr set."""
    keep = np.array(
        [getattr(mesh.materials[m], attr) for m in mesh.face_materials],
        dtype=bool,
    )
    return _submesh(mesh, keep)


def _filter_side(mesh: Mesh, *, drop_attr: str) -> Mesh:
    """Sub-mesh excluding faces whose material has drop_attr set."""
    keep = np.array(
        [not getattr(mesh.materials[m], drop_attr) for m in mesh.face_materials],
        dtype=bool,
    )
    return _submesh(mesh, keep)


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


# A vertex that shifts by more than this (OBJ units) between the closed and fully
# open pose counts as part of the swinging leaf.
_DOOR_MOTION_EPS = 1e-4


def _door_leaf_face_mask(closed: Mesh, opened: Mesh) -> NDArray[np.bool_]:
    """Classify each face as part of the swinging leaf (True) or the static frame
    (False) by whether any of its vertices move between the closed and open pose."""
    moved_vertex = np.abs(closed.vertices - opened.vertices).max(axis=1) > _DOOR_MOTION_EPS
    moved_face: NDArray[np.bool_] = moved_vertex[closed.faces].any(axis=1)
    if not moved_face.any():
        return np.ones(closed.faces.shape[0], dtype=bool)
    return moved_face


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
    if all(
        m.vertices.shape == sampled[0].vertices.shape
        and m.faces.shape == sampled[0].faces.shape
        for m in sampled[1:]
    ):
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


def _corners_by_dir(units_per_tile: float) -> list[tuple[float, float]]:
    """Per-direction half-tile corner offsets in OBJ units, scaled to the
    authored render scale."""
    h = units_per_tile / 2.0
    return [(h, h), (-h, h), (-h, -h), (h, -h)]


def _render_4_rotations(
    context: Context,
    mesh: Mesh,
    cx: float,
    cz: float,
    corners: list[tuple[float, float]] | None = None,
) -> list[IndexedImage]:
    """Render the 4 cardinal rotations of `mesh`, anchoring each direction's
    world origin at the tile's per-direction corner."""
    if corners is None:
        corners = _CORNER_BY_DIR
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(4)]
    out: list[IndexedImage] = []
    for d in range(4):
        ox, oz = corners[d]
        translation = np.array([-(cx + ox), 0.0, -(cz + oz)], dtype=np.float64)
        out.append(_render_scene_view(context, mesh, translation, VIEWS[d]))
    return out


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
    bx, by = draw
    return IndexedImage(
        width=img.width,
        height=img.height,
        x_offset=_SCENERY_BUTTON_W // 2 - bx - img.width // 2,
        y_offset=_SCENERY_BUTTON_H // 2 - by - img.height // 2,
        pixels=img.pixels,
    )


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

    if normal.faces.shape[0] == 0:
        images = [IndexedImage.blank(1, 1)]
    else:
        preview = _render_scene_view(context, normal, np.zeros(3, dtype=np.float64), VIEWS[0])
        images = [_center_in_button(preview, _PATH_ADDITION_PREVIEW_DRAW)]

    normal_edges = edge_sprites(normal)
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
