"""
Scenery sprite rendering.

Unlike vehicles (16 sprite groups of pitch/roll/yaw track rotations), scenery
needs only the cardinal rotations: VIEWS[i] == rotate_y(i * pi/2), so rendering
the prepared scene under the first `num_rotations` views yields the rotation
sprites OpenRCT2 expects. Colour remap (primary/secondary) is baked per-pixel by
the palette region of remappable materials, exactly as for vehicles — it does
not add sprites here.
"""

from typing import Any

import numpy as np
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.geometry import assign_faces_to_tiles, combine_model_world, subset_mesh
from openrct2_x7_renderer.mesh import Mesh
from openrct2_x7_renderer.ray_trace import VIEWS, Context, FinalizedScene
from openrct2_x7_renderer.types import IndexedImage, Model

_IDENTITY3 = np.eye(3, dtype=np.float64)


def _render_scene_view(
    context: Context, mesh: Mesh, translation: np.ndarray, view: np.ndarray
) -> IndexedImage:
    """Render a single model under a single view in its own scene. Used by the
    wall and large-scenery paths, which re-anchor (different `translation`) per
    view and so cannot share one finalized scene."""
    with context.begin_render() as scene:
        with scene.add_model(mesh, _IDENTITY3, translation, 0).finalize() as ready:
            return ready.render_view(view)


def _render_scene_views(
    context: Context, mesh: Mesh, translation: np.ndarray, views: list[np.ndarray]
) -> list[IndexedImage]:
    """Render a single model under several views, sharing one finalized scene
    (same anchor for every view)."""
    with context.begin_render() as scene:
        with scene.add_model(mesh, _IDENTITY3, translation, 0).finalize() as ready:
            return [ready.render_view(v) for v in views]

# OpenRCT2 anchors large-scenery sprites at the tile's reference CORNER (paint
# offset {0,0}), not its centre like small scenery ({15,15}). Empirically, the
# anchor corner the engine expects ROTATES with the sprite direction: rendering
# direction d with the world origin at tile-centre + corner[d] reproduces the
# vanilla per-sprite offsets (x_off=-32, base aligned to the tile) for all four
# directions. Derived by matching SDN3's sprite offsets direction-by-direction.
_HALF_TILE = TILE_SIZE / 2.0
_H = _HALF_TILE
_CORNER_BY_DIR = [(_H, _H), (-_H, _H), (-_H, -_H), (_H, -_H)]

# Reserved preview/menu image slots that precede the per-tile sprites; OpenRCT2
# indexes per-tile sprites as `base + 4 + sequence*4 + direction`.
LARGE_SCENERY_PREVIEW_SLOTS = 4


# Animated small scenery reserves a leading group of 4 "base" sprites (the
# static depiction shown in the scenery picker and when zoomed out). The engine
# only paints these when SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED is set, which
# also shifts the in-world animation index by +4 (Paint.SmallScenery.cpp:294)
# and suppresses the always-on static base parent draw (line 193) that would
# otherwise overlay a frozen pose-0 ghost on the animation.
ANIMATED_BASE_SLOTS = 4


def count_small_scenery_sprites(num_rotations: int, num_pose_groups: int = 1) -> int:
    """Static scenery: `num_rotations` sprites. Animated scenery: a 4-sprite base
    group, then one group of 4 rotation sprites per pose (the engine's frame
    index hardcodes * 4 and adds +4 past the base), so
    `4 + num_pose_groups * 4` regardless of `num_rotations`."""
    if num_pose_groups > 1:
        return ANIMATED_BASE_SLOTS + num_pose_groups * 4
    return num_rotations


def render_small_scenery(scene: FinalizedScene, num_rotations: int = 4) -> list[IndexedImage]:
    """Render the prepared (finalized) scene under the first `num_rotations`
    cardinal views."""
    return [scene.render_view(VIEWS[i]) for i in range(num_rotations)]


def _render_pose_rotations(
    context: Context, meshes: list[Mesh], model: Model, frame: int
) -> list[IndexedImage]:
    """Bake pose `frame`'s placements and render all 4 cardinal rotations,
    anchored at the tile centre (model origin)."""
    combined = combine_model_world(meshes, model, frame=frame)
    return _render_scene_views(
        context, combined, np.zeros(3, dtype=np.float64), [VIEWS[d] for d in range(4)]
    )


def render_small_scenery_animated(
    context: Context, meshes: list[Mesh], model: Model, num_pose_groups: int
) -> list[IndexedImage]:
    """Render an animated small-scenery sprite set in the engine's image order:
    a leading 4-sprite base group (rendered from pose 0; the static depiction the
    engine paints in the picker / when zoomed out), then per pose group its 4
    cardinal rotations (group-major, direction-minor). Matches vanilla animated
    scenery, whose in-world animation index is `4 + frame_offsets[frame] * 4 +
    direction` (Paint.SmallScenery.cpp:293-296)."""
    images: list[IndexedImage] = _render_pose_rotations(context, meshes, model, 0)
    for g in range(num_pose_groups):
        images.extend(_render_pose_rotations(context, meshes, model, g))
    return images


def count_large_scenery_sprites(num_tiles: int) -> int:
    """4 reserved preview images + one sprite per (tile, rotation)."""
    return LARGE_SCENERY_PREVIEW_SLOTS + 4 * num_tiles


# Walls: a wall sprite is the panel along one diagonal, anchored at ONE END (a
# tile corner) -- the engine places it on the correct edge via its paint offset,
# so the sprite itself need not be on an edge. The panel is shifted to its -Z end
# and rendered under VIEWS[1] (sprite 0) and VIEWS[0] (sprite 1). The author
# models the panel running along OBJ +Z.
_WALL_FLAT_VIEWS = (1, 0)
# Per-view half-pixel grid alignment. A panel spanning the full tile edge projects
# to 34px when its end sits exactly on the world origin -- straddling the pixel
# grid so AA spills an extra column on each outer end, overlapping the neighbour by
# 2px (the visible "bleed"). Nudging the anchor in Z lands it cleanly on 33px. The
# two diagonal views fall on the grid at DIFFERENT sub-pixel phases (the iso
# half-pixel asymmetry vanilla bakes into its hand-drawn art), so each needs its
# own nudge: a single shared shift can match only one. With these, both flat
# sprites hit vanilla exactly -- VIEWS[1] -> x_off -31 base 15, VIEWS[0] -> x_off
# -1 base 16. One tile edge projects to 32px (UNITS_PER_TILE / UNITS_PER_PIXEL),
# so a half pixel is TILE_SIZE / 64.
_HALF_PIXEL = TILE_SIZE / 64.0
_WALL_VIEW_SHIFT = {
    1: -_HALF_TILE + 3.0 * _HALF_PIXEL,
    0: -_HALF_TILE + 1.0 * _HALF_PIXEL,
}
# One land-height step as a vertical shear of the panel end, in OBJ Y. Calibrated
# so the slope RISE matches vanilla exactly: a slope-up sprite is +16px taller
# than flat in BOTH diagonal views (the terrain's one-step rise). 1.34 is the
# centre of the stable 1.32-1.36 window; below it (e.g. the old 1.26) the rise
# rounds to +15px and the wall sits 1px low against sloped terrain.
_WALL_SLOPE_RISE = 1.34
# Slope-DOWN lifts the whole panel by ~one slope step so it anchors at the raised
# (high) corner. Tuned (with RISE=1.34) to vanilla's slope-down profile: base 0/1
# and rise -15px in both views. 1.2975 is the centre of the stable 1.290-1.305
# window; it sets the base/lift without disturbing the matched x-offsets.
_WALL_SLOPE_DOWN_RAISE = 1.2975


def _shear_wall(
    combined: Mesh, sign: float, rise: float = _WALL_SLOPE_RISE, y_raise: float = 0.0
) -> Mesh:
    """Ramp the panel's Y along its length (Z), raising the +Z end by
    `sign * rise` so it follows a sloped edge. `y_raise` lifts the whole panel
    (slope-down anchors at the raised corner). Both `rise` and `y_raise` are in
    OBJ units, so callers scale them with the authored render scale."""
    v = combined.vertices.astype(np.float64).copy()
    z = v[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    span = (zmax - zmin) or 1.0
    t = (z - zmin) / span  # 0 at -Z end, 1 at +Z end
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
    context: Context, mesh: Mesh, view_shift: dict[int, float] = _WALL_VIEW_SHIFT
) -> list[IndexedImage]:
    """Render a wall mesh under the two diagonal views, each end-anchored with its
    own per-view shift (the two views need different sub-pixel nudges to land on
    the grid -- see _WALL_VIEW_SHIFT). `view_shift` is in OBJ units, so callers
    scale it with the authored render scale."""
    out: list[IndexedImage] = []
    for v in _WALL_FLAT_VIEWS:
        translation = np.array((0.0, 0.0, view_shift[v]), dtype=np.float64)
        out.append(_render_scene_view(context, mesh, translation, VIEWS[v]))
    return out


def _submesh(mesh: Mesh, keep: np.ndarray) -> Mesh:
    """A mesh with only the faces selected by the boolean `keep` mask (vertices,
    normals and materials are shared by reference -- the renderer only touches
    referenced ones)."""
    return Mesh(
        vertices=mesh.vertices,
        normals=mesh.normals,
        uvs=mesh.uvs,
        faces=mesh.faces[keep],
        face_materials=mesh.face_materials[keep],
        materials=mesh.materials,
    )


def _filter_glass(mesh: Mesh, want_glass: bool) -> Mesh:
    """Sub-mesh of the faces whose material's `is_glass` matches `want_glass`."""
    keep = np.array(
        [mesh.materials[m].is_glass == want_glass for m in mesh.face_materials],
        dtype=bool,
    )
    return _submesh(mesh, keep)


def _filter_side(mesh: Mesh, *, drop_attr: str) -> Mesh:
    """Sub-mesh excluding faces whose material has `drop_attr` set. Used to peel
    the front block (drop `is_back`) and back block (drop `is_front`) for
    double-sided walls; untagged faces have neither set so survive both."""
    keep = np.array(
        [not getattr(mesh.materials[m], drop_attr) for m in mesh.face_materials],
        dtype=bool,
    )
    return _submesh(mesh, keep)


def _rotate_y180(mesh: Mesh) -> Mesh:
    """Rotate a mesh 180 deg about the vertical (Y) axis: negate X and Z on
    vertices and normals. A proper rotation (winding/handedness preserved), so
    the rear faces turn to face the camera. The panel's Z-range is symmetric so
    it is unchanged -- the same end-anchor and slope shear apply -- while the
    content mirrors left-right, as a wall does when viewed from behind."""
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
    view_shift: dict[int, float] = _WALL_VIEW_SHIFT,
) -> list[IndexedImage]:
    """One wall image block: 2 flat sprites, plus (if `slope`) 4 slope-sheared
    sprites -- offsets 2,3 = slope-up, 4,5 = slope-down, each in the two diagonal
    orientations. Empty meshes yield blank placeholders so the block stays the
    right length. The OBJ-unit anchors (`rise`, `down_raise`, `view_shift`) are
    passed in pre-scaled to the authored render scale."""
    n = 6 if slope else 2
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(n)]
    images = _render_wall_pair(context, mesh, view_shift)  # offsets 0,1 (flat)
    if slope:
        # slope-up: far end raised. slope-down: far end lowered AND the whole
        # panel lifted one step (it anchors at the raised/high corner).
        images += _render_wall_pair(context, _shear_wall(mesh, +1.0, rise), view_shift)  # 2,3 up
        images += _render_wall_pair(
            context, _shear_wall(mesh, -1.0, rise, y_raise=down_raise), view_shift
        )  # 4,5 down
    return images


def render_wall(
    context: Context,
    combined: Mesh,
    allowed_on_slope: bool,
    has_glass: bool = False,
    is_double_sided: bool = False,
    units_per_tile: float = TILE_SIZE,
) -> list[IndexedImage]:
    """Render a wall sprite set.

    Plain: a single block of 2 (flat) or 6 (slope-allowed) sprites.

    Glass: the engine always layers a translucent overlay sprite at
    `imageIndex + 6` (Paint.Wall.cpp:148), so glass implies the full 6-slot
    block layout -- 6 opaque body sprites (non-glass faces) at offsets 0..5,
    then 6 glass-only overlay sprites at offsets 6..11, for 12 total. Matches
    every vanilla glass wall (all are slope-allowed, 12 images).

    Double-sided: the rear-facing paint directions (1,2) read sprites at
    `imageOffset + 6` (Paint.Wall.cpp:236-262), so the back block occupies the
    same screen footprint as the front. Front block (0..5) = faces not tagged
    *Back*; back block (6..11) = faces not tagged *Front*, rotated 180 deg so the
    rear faces the camera. 12 total. (The glass x double `+12` combo is not
    generated -- callers must not set both.)

    `units_per_tile` is the authored render scale; the OBJ-unit slope shear and
    per-view grid nudges are calibrated at TILE_SIZE, so they scale with it."""
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


def render_wall_flat(context: Context, combined: Mesh) -> list[IndexedImage]:
    """Render only the 2 flat wall sprites (kept for callers/tests)."""
    if combined.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in _WALL_FLAT_VIEWS]
    return _render_wall_pair(context, combined)


def _corners_by_dir(units_per_tile: float) -> list[tuple[float, float]]:
    """Per-direction half-tile corner offsets in OBJ units, scaled to the
    authored render scale (1 tile = `units_per_tile` OBJ units)."""
    h = units_per_tile / 2.0
    return [(h, h), (-h, h), (-h, -h), (h, -h)]


def _render_4_rotations(
    context: Context,
    mesh: Mesh,
    cx: float,
    cz: float,
    corners: list[tuple[float, float]] = _CORNER_BY_DIR,
) -> list[IndexedImage]:
    """Render the 4 cardinal rotations of `mesh`, anchoring each direction's
    world origin at the tile's per-direction corner (centre + corner offset).
    Returns 4 blank sprites if the mesh has no faces."""
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
    tile_centers_xz: np.ndarray,
    units_per_tile: float = TILE_SIZE,
) -> list[IndexedImage]:
    """Render a large-scenery sprite set in OpenRCT2 image order:
    4 preview sprites (whole structure, centred), then per tile (in `tiles`
    order) its 4 rotations. Each tile's geometry is the faces nearest that
    tile's centre, re-anchored so the tile origin maps to the sprite origin.

    `units_per_tile` is the authored render scale; the per-direction corner
    anchors are half a tile in OBJ units, so they scale with it.
    """
    images: list[IndexedImage] = []
    corners = _corners_by_dir(units_per_tile)

    # Preview slots 0-3: the whole structure, anchored at the footprint centre.
    anchor = (
        tile_centers_xz.mean(axis=0) if tile_centers_xz.shape[0] else np.zeros(2, dtype=np.float64)
    )
    images.extend(
        _render_4_rotations(context, combined, float(anchor[0]), float(anchor[1]), corners)
    )

    # Per-tile sprites, anchored at each tile's per-direction corner.
    assign = assign_faces_to_tiles(combined, tile_centers_xz)
    for seq in range(tile_centers_xz.shape[0]):
        sub = subset_mesh(combined, assign == seq)
        cx, cz = tile_centers_xz[seq]
        images.extend(_render_4_rotations(context, sub, float(cx), float(cz), corners))
    return images
