"""
Tests for the pure wall-geometry transforms in the scenery sprite renderer.
"""

import numpy as np
from openrct2_scenery_generator.sprite_renderer import (
    _CORNER_BY_DIR,
    _anchor_corners,
    _corners_by_dir,
    _filter_glass,
    _filter_side,
    _shear_wall,
    _submesh,
    _wall_view_translation,
    small_scenery_paint_anchor,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.mesh import Material, Mesh


def _panel(materials=None, faces=None, face_materials=None):
    verts = np.array(
        [[0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1]], dtype=np.float32
    )
    if faces is None:
        faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.uint32)
    if face_materials is None:
        face_materials = np.zeros(faces.shape[0], dtype=np.uint32)
    if materials is None:
        materials = [Material()]
    normals = np.tile([1.0, 0.0, 0.0], (verts.shape[0], 1)).astype(np.float32)
    return Mesh(
        vertices=verts,
        normals=normals,
        uvs=np.zeros((verts.shape[0], 2), dtype=np.float32),
        faces=faces,
        face_materials=face_materials,
        materials=materials,
    )


def _full_tile_panel(upt=2.0):
    """A panel spanning the whole tile edge: z in [-upt/2, +upt/2]."""
    p = _panel()
    p.vertices[:, 2] = p.vertices[:, 2] * upt - upt / 2.0
    return p


def test_shear_up_raises_far_end_only():
    out = _shear_wall(_full_tile_panel(), sign=+1.0, rise=2.0, units_per_tile=2.0)
    v = out.vertices
    near = v[v[:, 2] == -1.0]
    far = v[v[:, 2] == 1.0]
    assert np.allclose(np.sort(near[:, 1]), [0.0, 1.0])
    assert np.allclose(np.sort(far[:, 1]), [2.0, 3.0])


def test_shear_down_lowers_far_end():
    out = _shear_wall(_full_tile_panel(), sign=-1.0, rise=2.0, units_per_tile=2.0)
    far = out.vertices[out.vertices[:, 2] == 1.0]
    assert np.allclose(np.sort(far[:, 1]), [-2.0, -1.0])


def test_shear_y_raise_lifts_whole_panel():
    out = _shear_wall(_full_tile_panel(), sign=-1.0, rise=2.0, y_raise=5.0, units_per_tile=2.0)
    near = out.vertices[out.vertices[:, 2] == -1.0]
    assert np.allclose(np.sort(near[:, 1]), [5.0, 6.0])


def test_shear_partial_panel_rises_by_tile_fraction():
    # The ramp follows the tile span, not the panel's own extent: a panel
    # covering only the +Z half of the tile starts half a step up and reaches
    # the full rise at the tile edge.
    out = _shear_wall(_panel(), sign=+1.0, rise=2.0, units_per_tile=2.0)
    v = out.vertices
    centre = v[v[:, 2] == 0.0]
    edge = v[v[:, 2] == 1.0]
    assert np.allclose(np.sort(centre[:, 1]), [1.0, 2.0])
    assert np.allclose(np.sort(edge[:, 1]), [2.0, 3.0])


def test_shear_preserves_topology_and_x():
    panel = _panel()
    out = _shear_wall(panel, sign=+1.0, rise=1.34)
    assert np.array_equal(out.faces, panel.faces)
    assert out.materials is panel.materials
    assert np.allclose(out.vertices[:, 0], panel.vertices[:, 0])
    assert np.allclose(out.vertices[:, 2], panel.vertices[:, 2])


def test_shear_degenerate_flat_panel_stays_finite():
    flat = _panel()
    flat.vertices[:, 2] = 0.0
    out = _shear_wall(flat, sign=+1.0, rise=2.0)
    assert np.all(np.isfinite(out.vertices))


def test_wall_view_translations_reproduce_vanilla_anchors():
    # Vanilla wall sprites ("/" = columns [-31, 1], "\" = [-1, 31] from the
    # anchor) pin these down exactly; see WALLBR32 / WALLJB16.
    upt = 32.0  # one OBJ unit per world unit for easy reading
    assert np.allclose(_wall_view_translation(0, upt), [-1.0, 0.0, -16.0])
    assert np.allclose(_wall_view_translation(1, upt), [0.0, 0.0, -15.0])
    assert np.allclose(_wall_view_translation(2, upt), [1.0, 0.0, 16.0])
    assert np.allclose(_wall_view_translation(3, upt), [0.0, 0.0, 15.0])


def test_wall_view_translations_scale_with_units_per_tile():
    t_full = _wall_view_translation(1, 32.0)
    t_half = _wall_view_translation(1, 16.0)
    assert np.allclose(t_half, t_full / 2.0)


def test_wall_view_translations_are_point_symmetric():
    # Views 2/3 anchor the panel at the opposite end of the edge from views 0/1.
    upt = TILE_SIZE
    assert np.allclose(_wall_view_translation(2, upt), -_wall_view_translation(0, upt))
    assert np.allclose(_wall_view_translation(3, upt), -_wall_view_translation(1, upt))


def test_small_scenery_paint_anchor_default_is_none():
    assert small_scenery_paint_anchor("4/4", False, False) is None
    assert small_scenery_paint_anchor("1/4", False, False) is None
    assert small_scenery_paint_anchor("4/4+D", False, False) is None


def test_small_scenery_paint_anchor_half_tile_and_voffset():
    assert small_scenery_paint_anchor("2/4", False, False) == 3.0
    assert small_scenery_paint_anchor("4/4+D", True, False) == 3.0
    assert small_scenery_paint_anchor("4/4+D", True, True) == 1.0
    # Half-tile takes the engine's half-tile paint path regardless of voffset.
    assert small_scenery_paint_anchor("2/4", True, True) == 3.0


def test_small_scenery_paint_anchor_quarter_tile_ignores_voffset():
    # Quarter-tile shapes take the engine's quadrant paint path, where
    # VOFFSET_CENTRE only affects support heights, never the paint offset.
    assert small_scenery_paint_anchor("1/4", True, False) is None
    assert small_scenery_paint_anchor("1/4", True, True) is None
    assert small_scenery_paint_anchor("1/4+D", True, True) is None


def test_anchor_corners_match_tile_corner_pattern():
    # The anchor at the tile origin (0, 0) is exactly the large-scenery
    # reference corner pattern.
    assert np.allclose(_anchor_corners(0.0, TILE_SIZE), _CORNER_BY_DIR)


def test_anchor_corners_rotate_like_the_views():
    corners = _anchor_corners(3.0, 32.0)  # 13 world units from centre
    assert corners == [(13.0, 13.0), (-13.0, 13.0), (-13.0, -13.0), (13.0, -13.0)]


def test_corners_by_dir_default_matches_module_constant():
    assert _corners_by_dir(TILE_SIZE) == _CORNER_BY_DIR


def test_corners_by_dir_scales_with_render_scale():
    corners = _corners_by_dir(8.0)
    assert corners == [(4.0, 4.0), (-4.0, 4.0), (-4.0, -4.0), (4.0, -4.0)]


def test_submesh_keeps_selected_faces_and_shares_vertices():
    panel = _panel()
    sub = _submesh(panel, np.array([True, False]))
    assert sub.faces.shape[0] == 1
    assert np.array_equal(sub.faces[0], panel.faces[0])
    assert sub.vertices is panel.vertices
    assert sub.materials is panel.materials


def test_filter_glass_splits_by_is_glass():
    mats = [Material(), Material()]
    mats[1].is_glass = True
    panel = _panel(materials=mats, face_materials=np.array([0, 1], dtype=np.uint32))

    body = _filter_glass(panel, want_glass=False)
    glass = _filter_glass(panel, want_glass=True)
    assert body.faces.shape[0] == 1
    assert glass.faces.shape[0] == 1
    assert int(body.face_materials[0]) == 0
    assert int(glass.face_materials[0]) == 1


def test_filter_glass_all_opaque_yields_empty_glass_block():
    panel = _panel(materials=[Material()], face_materials=np.array([0, 0], dtype=np.uint32))
    assert _filter_glass(panel, want_glass=True).faces.shape[0] == 0
    assert _filter_glass(panel, want_glass=False).faces.shape[0] == 2


def test_filter_side_drops_tagged_faces_keeps_shared():
    shared, front, back = Material(), Material(), Material()
    front.is_front = True
    back.is_back = True
    verts = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1]], dtype=np.float32)
    panel = Mesh(
        vertices=verts,
        normals=np.tile([1.0, 0, 0], (4, 1)).astype(np.float32),
        uvs=np.zeros((4, 2), dtype=np.float32),
        faces=np.array([[0, 1, 2], [1, 3, 2], [0, 3, 1]], dtype=np.uint32),
        face_materials=np.array([0, 1, 2], dtype=np.uint32),
        materials=[shared, front, back],
    )
    front_block = _filter_side(panel, drop_attr="is_back")
    assert sorted(front_block.face_materials.tolist()) == [0, 1]
    back_block = _filter_side(panel, drop_attr="is_front")
    assert sorted(back_block.face_materials.tolist()) == [0, 2]
