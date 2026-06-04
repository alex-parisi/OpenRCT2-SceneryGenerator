"""Tests for the pure wall-geometry transforms in the scenery sprite renderer.

These helpers do the mesh maths the wall pipeline relies on (slope shear, the
180-degree rear-block rotation, per-direction tile corners, and the
glass/front-back face splits). None of them touch the native renderer, so they
are exercised directly here -- the calibrated *pixel* offsets are verified
in-game, but the geometry these produce can be checked numerically.
"""

import numpy as np
from openrct2_scenery_generator.sprite_renderer import (
    _CORNER_BY_DIR,
    _corners_by_dir,
    _filter_glass,
    _filter_side,
    _rotate_y180,
    _shear_wall,
    _submesh,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.mesh import Material, Mesh


def _panel(materials=None, faces=None, face_materials=None):
    """A unit panel in the X=0 plane running from z=0 (the -Z end) to z=1.

    Two triangles spanning the quad (0,0,0)-(0,0,1)-(0,1,0)-(0,1,1)."""
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


# --- _shear_wall -------------------------------------------------------------


def test_shear_up_raises_far_end_only():
    out = _shear_wall(_panel(), sign=+1.0, rise=2.0)
    v = out.vertices
    # -Z end (z=0) is unchanged; +Z end (z=1) is raised by the full rise.
    near = v[v[:, 2] == 0.0]
    far = v[v[:, 2] == 1.0]
    assert np.allclose(near[:, 1], [0.0, 1.0])
    assert np.allclose(np.sort(far[:, 1]), [2.0, 3.0])


def test_shear_down_lowers_far_end():
    out = _shear_wall(_panel(), sign=-1.0, rise=2.0)
    far = out.vertices[out.vertices[:, 2] == 1.0]
    # +Z end drops by the rise; original ys were 0 and 1 -> -2 and -1.
    assert np.allclose(np.sort(far[:, 1]), [-2.0, -1.0])


def test_shear_y_raise_lifts_whole_panel():
    out = _shear_wall(_panel(), sign=-1.0, rise=2.0, y_raise=5.0)
    near = out.vertices[out.vertices[:, 2] == 0.0]
    # The -Z (t=0) end gets only the bulk lift, no shear contribution.
    assert np.allclose(np.sort(near[:, 1]), [5.0, 6.0])


def test_shear_preserves_topology_and_x():
    panel = _panel()
    out = _shear_wall(panel, sign=+1.0, rise=1.34)
    assert np.array_equal(out.faces, panel.faces)
    assert out.materials is panel.materials
    # Only Y is touched: X and Z survive intact.
    assert np.allclose(out.vertices[:, 0], panel.vertices[:, 0])
    assert np.allclose(out.vertices[:, 2], panel.vertices[:, 2])


def test_shear_degenerate_zero_span_does_not_divide_by_zero():
    # A panel with no Z extent: span falls back to 1.0, so nothing blows up and
    # the (constant) shear term is applied uniformly.
    flat = _panel()
    flat.vertices[:, 2] = 0.0
    out = _shear_wall(flat, sign=+1.0, rise=2.0)
    assert np.all(np.isfinite(out.vertices))


# --- _rotate_y180 ------------------------------------------------------------


def test_rotate_y180_negates_x_and_z():
    panel = _panel()
    panel.vertices[:] = [[1, 0, 2], [1, 0, -2], [1, 1, 2], [1, 1, -2]]
    out = _rotate_y180(panel)
    assert np.allclose(out.vertices[:, 0], -panel.vertices[:, 0])
    assert np.allclose(out.vertices[:, 2], -panel.vertices[:, 2])
    # Y (the vertical axis we rotate about) is untouched.
    assert np.allclose(out.vertices[:, 1], panel.vertices[:, 1])


def test_rotate_y180_also_flips_normals():
    out = _rotate_y180(_panel())
    # +X-facing normals turn to -X (the rear faces the camera after rotation).
    assert np.allclose(out.normals[:, 0], -1.0)


def test_rotate_y180_is_a_proper_rotation():
    # Applying it twice is the identity (det = +1, not a reflection).
    panel = _panel()
    twice = _rotate_y180(_rotate_y180(panel))
    assert np.allclose(twice.vertices, panel.vertices)
    assert np.allclose(twice.normals, panel.normals)


# --- _corners_by_dir ---------------------------------------------------------


def test_corners_by_dir_default_matches_module_constant():
    assert _corners_by_dir(TILE_SIZE) == _CORNER_BY_DIR


def test_corners_by_dir_scales_with_render_scale():
    corners = _corners_by_dir(8.0)
    assert corners == [(4.0, 4.0), (-4.0, 4.0), (-4.0, -4.0), (4.0, -4.0)]


# --- _submesh / _filter_glass / _filter_side --------------------------------


def test_submesh_keeps_selected_faces_and_shares_vertices():
    panel = _panel()
    sub = _submesh(panel, np.array([True, False]))
    assert sub.faces.shape[0] == 1
    assert np.array_equal(sub.faces[0], panel.faces[0])
    # Vertices/materials are shared by reference (the renderer only reads the
    # ones the surviving faces index).
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
    # Three faces: shared (untagged), front-only, back-only.
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
    # Front block drops back faces -> shared + front survive.
    front_block = _filter_side(panel, drop_attr="is_back")
    assert sorted(front_block.face_materials.tolist()) == [0, 1]
    # Back block drops front faces -> shared + back survive.
    back_block = _filter_side(panel, drop_attr="is_front")
    assert sorted(back_block.face_materials.tolist()) == [0, 2]
