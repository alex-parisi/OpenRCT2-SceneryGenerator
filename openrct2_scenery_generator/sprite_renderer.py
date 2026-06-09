"""
Scenery sprite rendering.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.geometry import assign_faces_to_tiles, combine_model_world, subset_mesh
from openrct2_x7_renderer.mesh import Mesh
from openrct2_x7_renderer.ray_trace import VIEWS, Context, FinalizedScene
from openrct2_x7_renderer.types import IndexedImage, Model

from .constants import DOOR_NUM_IMAGES, DOOR_SAMPLE_FRAMES, WALL_ANIMATION_FRAMES

_IDENTITY3 = np.eye(3, dtype=np.float64)


def _render_scene_view(
    context: Context, mesh: Mesh, translation: NDArray[np.float64], view: NDArray[np.float64]
) -> IndexedImage:
    """Render a single model under a single view in its own scene."""
    with context.begin_render() as scene:
        with scene.add_model(mesh, _IDENTITY3, translation, 0).finalize() as ready:
            return ready.render_view(view)


def _render_scene_views(
    context: Context, mesh: Mesh, translation: NDArray[np.float64], views: list[NDArray[np.float64]]
) -> list[IndexedImage]:
    """Render a single model under several views, sharing one finalized scene."""
    with context.begin_render() as scene:
        with scene.add_model(mesh, _IDENTITY3, translation, 0).finalize() as ready:
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


def _render_pose_rotations(
    context: Context, meshes: list[Mesh], model: Model, frame: int
) -> list[IndexedImage]:
    """Bake pose frame's placements and render all 4 cardinal rotations,
    anchored at the tile center."""
    combined = combine_model_world(meshes, model, frame=frame)
    return _render_scene_views(
        context, combined, np.zeros(3, dtype=np.float64), [VIEWS[d] for d in range(4)]
    )


def render_small_scenery_animated(
    context: Context,
    meshes: list[Mesh],
    model: Model,
    num_pose_groups: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[IndexedImage]:
    """Render an animated small-scenery sprite set in the engine's image order"""
    base = _render_pose_rotations(context, meshes, model, 0)
    if progress is not None:
        progress(1, num_pose_groups)
    images: list[IndexedImage] = list(base) + list(base)
    for g in range(1, num_pose_groups):
        images.extend(_render_pose_rotations(context, meshes, model, g))
        if progress is not None:
            progress(g + 1, num_pose_groups)
    return images


def count_large_scenery_sprites(num_tiles: int) -> int:
    """4 reserved preview images + one sprite per (tile, rotation)."""
    return LARGE_SCENERY_PREVIEW_SLOTS + 4 * num_tiles


# Walls:
_WALL_FLAT_VIEWS = (1, 0)
# Per-view half-pixel grid alignment.
_HALF_PIXEL = TILE_SIZE / 64.0
_WALL_VIEW_SHIFT = {
    1: -_HALF_TILE + 3.0 * _HALF_PIXEL,
    0: -_HALF_TILE + 1.0 * _HALF_PIXEL,
}
# One land-height step as a vertical shear of the panel end, in OBJ Y.
_WALL_SLOPE_RISE = 1.34
_WALL_SLOPE_DOWN_RAISE = 1.2975


def _shear_wall(
    combined: Mesh, sign: float, rise: float = _WALL_SLOPE_RISE, y_raise: float = 0.0
) -> Mesh:
    """Ramp the panel's Y along its length (Z), raising the +Z end by
    `sign * rise` so it follows a sloped edge."""
    v = combined.vertices.astype(np.float64).copy()
    z = v[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    span = (z_max - z_min) or 1.0
    t = (z - z_min) / span
    v[:, 1] += sign * rise * t + y_raise
    return Mesh(
        vertices=v.astype(np.float32),
        normals=combined.normals,
        uvs=combined.uvs,
        faces=combined.faces,
        face_materials=combined.face_materials,
        materials=combined.materials,
    )


def _render_wall_pair(
    context: Context, mesh: Mesh, view_shift: dict[int, float] | None = None
) -> list[IndexedImage]:
    """Render a wall mesh under the two diagonal views, each end-anchored with its
    own per-view shift."""
    if view_shift is None:
        view_shift = _WALL_VIEW_SHIFT
    out: list[IndexedImage] = []
    for v in _WALL_FLAT_VIEWS:
        translation = np.array((0.0, 0.0, view_shift[v]), dtype=np.float64)
        out.append(_render_scene_view(context, mesh, translation, VIEWS[v]))
    return out


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


def _rotate_y180(mesh: Mesh) -> Mesh:
    """Rotate a mesh 180 deg about the vertical (Y) axis: negate X and Z on
    vertices and normals."""
    v = mesh.vertices.copy()
    v[:, 0] *= -1.0
    v[:, 2] *= -1.0
    n = mesh.normals.copy()
    n[:, 0] *= -1.0
    n[:, 2] *= -1.0
    return Mesh(
        vertices=v,
        normals=n,
        uvs=mesh.uvs,
        faces=mesh.faces,
        face_materials=mesh.face_materials,
        materials=mesh.materials,
    )


def _render_wall_block(
    context: Context,
    mesh: Mesh,
    slope: bool,
    *,
    rise: float = _WALL_SLOPE_RISE,
    down_raise: float = _WALL_SLOPE_DOWN_RAISE,
    view_shift: dict[int, float] | None = None,
) -> list[IndexedImage]:
    """One wall image block: 2 flat sprites, plus (if `slope`) 4 slope-sheared
    sprites: offsets 2,3 = slope-up, 4,5 = slope-down, each in the two diagonal
    orientations."""
    if view_shift is None:
        view_shift = _WALL_VIEW_SHIFT
    n = 6 if slope else 2
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(n)]
    images = _render_wall_pair(context, mesh, view_shift)
    if slope:
        images += _render_wall_pair(context, _shear_wall(mesh, +1.0, rise), view_shift)
        images += _render_wall_pair(
            context, _shear_wall(mesh, -1.0, rise, y_raise=down_raise), view_shift
        )
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
        "rise": _WALL_SLOPE_RISE * s,
        "down_raise": _WALL_SLOPE_DOWN_RAISE * s,
        "view_shift": {v: sh * s for v, sh in _WALL_VIEW_SHIFT.items()},
    }
    if has_glass:
        body = _filter_glass(combined, want_glass=False)
        glass = _filter_glass(combined, want_glass=True)
        return _render_wall_block(context, body, slope=True, **anchors) + _render_wall_block(
            context, glass, slope=True, **anchors
        )
    if is_double_sided:
        front = _filter_side(combined, drop_attr="is_back")
        back = _rotate_y180(_filter_side(combined, drop_attr="is_front"))
        return _render_wall_block(context, front, slope=True, **anchors) + _render_wall_block(
            context, back, slope=True, **anchors
        )
    return _render_wall_block(context, combined, slope=allowed_on_slope, **anchors)


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
    s = units_per_tile / TILE_SIZE
    view_shift = {v: sh * s for v, sh in _WALL_VIEW_SHIFT.items()}
    images: list[IndexedImage] = []
    for f in range(WALL_ANIMATION_FRAMES):
        combined = combine_model_world(meshes, model, frame=f)
        if combined.faces.shape[0] == 0:
            images += [IndexedImage.blank(1, 1), IndexedImage.blank(1, 1)]
        else:
            images += _render_wall_pair(context, combined, view_shift)
        if progress is not None:
            progress(f + 1, WALL_ANIMATION_FRAMES)
    return images


# A door's two screen orientations
_DOOR_ORIENTATION_VIEWS = (1, 0)


def _mirror_wall_x(mesh: Mesh) -> Mesh:
    """Reflect a wall mesh across the X=0 plane (the wall's thin axis): negate X
    on vertices and normals and reverse each triangle's winding so faces stay
    outward-facing."""
    v = mesh.vertices.copy()
    v[:, 0] *= -1.0
    n = mesh.normals.copy()
    n[:, 0] *= -1.0
    return Mesh(
        vertices=v,
        normals=n,
        uvs=mesh.uvs,
        faces=mesh.faces[:, ::-1].copy(),
        face_materials=mesh.face_materials,
        materials=mesh.materials,
    )


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
    """Render a door-wall sprite set in the engine's image order."""
    s = units_per_tile / TILE_SIZE
    view_shift = {v: sh * s for v, sh in _WALL_VIEW_SHIFT.items()}
    blank = IndexedImage.blank(1, 1)

    def render(mesh: Mesh, view: int) -> IndexedImage:
        if mesh.faces.shape[0] == 0:
            return blank
        translation = np.array((0.0, 0.0, view_shift[view]), dtype=np.float64)
        return _render_scene_view(context, mesh, translation, VIEWS[view])

    sampled = [
        combine_model_world(meshes, model, frame=f) for f in range(DOOR_SAMPLE_FRAMES)
    ]
    leaf_mask = _door_leaf_face_mask(sampled[0], sampled[-1])
    frame_mesh = _submesh(sampled[0], ~leaf_mask)

    forward_leaves = [_submesh(m, leaf_mask) for m in sampled[1:DOOR_SAMPLE_FRAMES]]
    leaves = [
        _submesh(sampled[0], leaf_mask),
        *forward_leaves,
        *(_mirror_wall_x(m) for m in forward_leaves),
    ]

    frame_imgs = {view: render(frame_mesh, view) for view in _DOOR_ORIENTATION_VIEWS}

    images: list[IndexedImage] = []
    for gi, leaf in enumerate(leaves):
        for view in _DOOR_ORIENTATION_VIEWS:
            images += [render(leaf, view), frame_imgs[view]]
        if progress is not None:
            progress(gi + 1, len(leaves))
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
