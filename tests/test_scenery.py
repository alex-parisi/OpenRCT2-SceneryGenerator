"""
Tests for the small-scenery generator
"""

import numpy as np
import pytest
from openrct2_scenery_generator.exporter import build_small_scenery_json
from openrct2_scenery_generator.loader import LoadError, build_small_scenery
from openrct2_scenery_generator.sprite_renderer import (
    count_small_scenery_sprites,
    render_small_scenery,
)
from openrct2_x7_renderer.types import IndexedImage


def _stub_image() -> IndexedImage:
    return IndexedImage(1, 1, 0, 0, np.zeros((1, 1), dtype=np.uint8))


class _FakeScene:
    """Stands in for FinalizedScene: every render returns a 1x1 dummy sprite, so
    sprite-count tests run without Embree."""

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def render_view(self, _view):
        return _stub_image()

    def render_silhouette(self, _view):
        return _stub_image()

    def end_render(self):
        pass


class _FakeBuilder:
    """Stands in for SceneBuilder."""

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def add_model(self, *_a, **_k):
        return self

    def finalize(self):
        return _FakeScene()


class _FakeContext:
    def begin_render(self):
        return _FakeBuilder()


def test_count_matches_render():
    assert count_small_scenery_sprites(4) == 4
    assert len(render_small_scenery(_FakeScene(), num_rotations=4)) == 4


def _make_scenery(tmp_path, **overrides):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_small.test",
        "name": "Test",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "shape": "4/4",
        **overrides,
    }
    mesh = load_mesh(tmp_path / "m.obj")
    return build_small_scenery(config, [mesh])


def test_build_json_shape(tmp_path):
    obj = _make_scenery(tmp_path, price=3.0, has_primary_colour=True)
    j = build_small_scenery_json(obj)
    assert j["objectType"] == "scenery_small"
    assert j["id"] == "openrct2sg.scenery_small.test"
    props = j["properties"]
    assert props["shape"] == "4/4"
    assert props["price"] == 3.0
    assert props["isRotatable"] is True
    assert props["hasPrimaryColour"] is True
    assert j["strings"]["name"]["en-GB"] == "Test"


def test_build_json_tertiary_colour(tmp_path):
    obj = _make_scenery(tmp_path, has_tertiary_colour=True)
    props = build_small_scenery_json(obj)["properties"]
    assert props["hasTertiaryColour"] is True

    obj = _make_scenery(tmp_path)
    props = build_small_scenery_json(obj)["properties"]
    assert props["hasTertiaryColour"] is False


def test_rotatable_defaults_true(tmp_path):
    obj = _make_scenery(tmp_path)
    assert obj.is_rotatable is True
    assert obj.num_rotations == 4
    # The engine paints image + direction even for non-rotatable objects (it
    # places them at a random direction), so 4 sprites are always rendered.
    obj2 = _make_scenery(tmp_path, is_rotatable=False)
    assert obj2.is_rotatable is False
    assert obj2.num_rotations == 4


def test_bad_shape_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_scenery(tmp_path, shape="5/4")


def _animation_block(poses):
    """Build an `animation` block with `poses` pose groups, ping-ponging."""
    offsets = list(range(poses)) + list(range(poses - 2, 0, -1))
    return {
        "delay": 1,
        "mask": 7,
        "frame_offsets": offsets,
        "frames": [
            [{"mesh_index": 0, "position": [0, 0, 0], "orientation": [0, 90 * g, 0]}]
            for g in range(poses)
        ],
    }


def _make_animated(tmp_path, poses=3, **overrides):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_small.anim",
        "name": "Anim",
        "shape": "4/4",
        "animation": _animation_block(poses),
        **overrides,
    }
    mesh = load_mesh(tmp_path / "m.obj")
    return build_small_scenery(config, [mesh])


def test_animated_pose_groups_and_count(tmp_path):
    obj = _make_animated(tmp_path, poses=3)
    assert obj.is_animated
    assert obj.num_pose_groups == 3
    assert len(obj.model.meshes) == 1
    assert len(obj.model.meshes[0]) == 3
    assert (
        count_small_scenery_sprites(
            obj.num_rotations, obj.num_pose_groups, animated=obj.is_animated
        )
        == 16
    )


def test_animated_json_shape(tmp_path):
    obj = _make_animated(tmp_path, poses=3)
    props = build_small_scenery_json(obj)["properties"]
    assert props["isAnimated"] is True
    assert props["animationDelay"] == 1
    assert props["animationMask"] == 7
    assert props["numFrames"] == len(obj.frame_offsets)
    assert props["frameOffsets"] == obj.frame_offsets
    assert max(props["frameOffsets"]) + 1 == 3
    assert props["SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED"] is True


def test_animated_render_order_and_count(tmp_path):
    from openrct2_scenery_generator.sprite_renderer import render_small_scenery_animated

    obj = _make_animated(tmp_path, poses=3)
    imgs = render_small_scenery_animated(
        _FakeContext(), obj.meshes, obj.model, obj.num_pose_groups
    )
    assert len(imgs) == 16


def test_animated_frame_offset_pose_mismatch_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_animated(
            tmp_path,
            animation={
                "delay": 0,
                "mask": 3,
                "frame_offsets": [0, 1, 2, 3],
                "frames": [
                    [{"mesh_index": 0, "position": [0, 0, 0]}],
                    [{"mesh_index": 0, "position": [0, 0, 0]}],
                ],
            },
        )


def test_animated_negative_offset_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_animated(
            tmp_path,
            animation={
                "frame_offsets": [0, -1],
                "frames": [[{"mesh_index": 0, "position": [0, 0, 0]}]],
            },
        )


from openrct2_scenery_generator.exporter import build_large_scenery_json  # noqa: E402
from openrct2_scenery_generator.loader import build_large_scenery  # noqa: E402
from openrct2_scenery_generator.sprite_renderer import (  # noqa: E402
    count_large_scenery_sprites,
    render_large_scenery,
)
from openrct2_x7_renderer.geometry import combine_model_world  # noqa: E402


@pytest.mark.parametrize("tiles,expected", [(1, 8), (2, 12), (4, 20)])
def test_large_count(tiles, expected):
    assert count_large_scenery_sprites(tiles) == expected


from openrct2_scenery_generator.exporter import build_wall_scenery_json  # noqa: E402
from openrct2_scenery_generator.loader import build_wall_scenery  # noqa: E402
from openrct2_scenery_generator.sprite_renderer import render_wall  # noqa: E402


def _make_wall(tmp_path, *, glass=False, **overrides):
    (tmp_path / "wall.mtl").write_text(
        "newmtl Frame\nKd 0.5 0.5 0.5\nnewmtl Glass\nKd 0.2 0.2 0.8\n"
    )
    (tmp_path / "w.obj").write_text(
        "mtllib wall.mtl\n"
        "v 0 0 0\nv 0 0 1\nv 0 1 0\nv 0 1 1\n"
        "usemtl Frame\nf 1 2 3\n"
        "usemtl Glass\nf 2 4 3\n"
    )
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_wall.test",
        "name": "Test Wall",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "has_glass": glass,
        **overrides,
    }
    mesh = load_mesh(tmp_path / "w.obj")
    return build_wall_scenery(config, [mesh])


def test_glass_material_classified(tmp_path):
    obj = _make_wall(tmp_path, glass=True)
    names = {m.is_glass for m in obj.meshes[0].materials}
    assert names == {True, False}  # one glass, one non-glass material


@pytest.mark.parametrize(
    "glass,double,slope,expected",
    [
        (False, False, False, 2),
        (False, False, True, 6),
        (True, False, False, 12),
        (True, False, True, 12),
        (False, True, False, 12),  # double-sided forces the 6+6 block layout
        (False, True, True, 12),
    ],
)
def test_wall_count_matches_render(tmp_path, glass, double, slope, expected):
    from openrct2_x7_renderer.geometry import combine_model_world

    obj = _make_wall(tmp_path, glass=glass, is_double_sided=double, is_allowed_on_slope=slope)
    assert obj.num_sprites == expected
    combined = combine_model_world(obj.meshes, obj.model)
    imgs = render_wall(
        _FakeContext(), combined, obj.is_allowed_on_slope, obj.has_glass, obj.is_double_sided
    )
    assert len(imgs) == expected


def _make_double_wall(tmp_path):
    (tmp_path / "d.mtl").write_text(
        "newmtl Frame\nKd 0.5 0.5 0.5\n"
        "newmtl FrontPanel\nKd 0.8 0.2 0.2\n"
        "newmtl BackPanel\nKd 0.2 0.2 0.8\n"
    )
    (tmp_path / "d.obj").write_text(
        "mtllib d.mtl\n"
        "v 0 0 0\nv 0 0 1\nv 0 1 0\nv 0 1 1\n"
        "usemtl Frame\nf 1 2 3\n"
        "usemtl FrontPanel\nf 2 4 3\n"
        "usemtl BackPanel\nf 1 4 2\n"
    )
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_wall.dbl",
        "name": "Double Wall",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "is_double_sided": True,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "d.obj")])


def test_front_back_material_classified(tmp_path):
    obj = _make_double_wall(tmp_path)
    by_side = {(m.is_front, m.is_back) for m in obj.meshes[0].materials}
    assert by_side == {(False, False), (True, False), (False, True)}


def test_double_sided_blocks_exclude_opposite_side(tmp_path, monkeypatch):
    from openrct2_scenery_generator import sprite_renderer as sr
    from openrct2_x7_renderer.geometry import combine_model_world

    seen = []

    def fake_block(_ctx, mesh, slope, **_anchors):
        seen.append(int(mesh.faces.shape[0]))
        return [IndexedImage(1, 1, 0, 0, np.zeros((1, 1), dtype=np.uint8))]

    monkeypatch.setattr(sr, "_render_wall_block", fake_block)
    obj = _make_double_wall(tmp_path)
    combined = combine_model_world(obj.meshes, obj.model)
    sr.render_wall(_FakeContext(), combined, True, has_glass=False, is_double_sided=True)
    assert seen == [2, 2]


def test_glass_double_combo_refused(tmp_path, caplog):
    obj = _make_wall(tmp_path, glass=True, is_double_sided=True)
    with caplog.at_level("WARNING"):
        props = build_wall_scenery_json(obj)["properties"]
    assert props.get("hasGlass") is True
    assert "isDoubleSided" not in props
    assert "combo is unsupported" in caplog.text


def _wall_animation_block(frames=8):
    """An `animation` block with `frames` wall poses (a slow horizontal slide)."""
    return {
        "frames": [
            [{"mesh_index": 0, "position": [0, 0, 0], "orientation": [0, 0, 0]}]
            for _ in range(frames)
        ]
    }


def _make_animated_wall(tmp_path, frames=8, **overrides):
    (tmp_path / "aw.obj").write_text("v 0 0 0\nv 0 0 1\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_wall.anim",
        "name": "Anim Wall",
        "animation": _wall_animation_block(frames),
        **overrides,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "aw.obj")])


def test_animated_wall_loads_eight_frames(tmp_path):
    obj = _make_animated_wall(tmp_path)
    assert obj.is_animated
    assert len(obj.model.meshes[0]) == 8


def test_animated_wall_wrong_frame_count_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_animated_wall(tmp_path, frames=6)


def test_animated_wall_non_object_animation_rejected(tmp_path):
    (tmp_path / "aw.obj").write_text("v 0 0 0\nv 0 0 1\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    with pytest.raises(LoadError):
        build_wall_scenery(
            {
                "id": "openrct2sg.scenery_wall.a",
                "name": "A",
                "animation": "not-an-object",
            },
            [load_mesh(tmp_path / "aw.obj")],
        )


def test_animated_wall_flag_without_frames_rejected(tmp_path):
    (tmp_path / "w.obj").write_text("v 0 0 0\nv 0 0 1\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    with pytest.raises(LoadError):
        build_wall_scenery(
            {
                "id": "openrct2sg.scenery_wall.a",
                "name": "A",
                "is_animated": True,
                "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
            },
            [load_mesh(tmp_path / "w.obj")],
        )


def test_animated_wall_render_count(tmp_path):
    from openrct2_scenery_generator.sprite_renderer import (
        count_wall_sprites,
        render_wall_animated,
    )

    obj = _make_animated_wall(tmp_path)
    imgs = render_wall_animated(_FakeContext(), obj.meshes, obj.model, obj.units_per_tile)
    assert len(imgs) == 16
    assert count_wall_sprites(is_animated=True) == 16
    # The non-animated counts mirror render_wall's block layout.
    assert count_wall_sprites() == 2
    assert count_wall_sprites(allowed_on_slope=True) == 6
    assert count_wall_sprites(has_glass=True) == 12
    assert count_wall_sprites(is_double_sided=True) == 12


def test_wall_num_sprites_covers_animated_and_door():
    from openrct2_scenery_generator.types import WallScenery

    assert WallScenery(is_animated=True).num_sprites == 16
    assert WallScenery(is_door=True).num_sprites == 36
    # A door's fixed image table wins over the other capability flags.
    assert WallScenery(is_door=True, has_glass=True).num_sprites == 36
    assert WallScenery(is_animated=True, is_allowed_on_slope=True).num_sprites == 16


def _make_door(tmp_path, frames=5, **overrides):
    (tmp_path / "dr.obj").write_text("v 0 0 0\nv 0 0 1\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    config = {
        "id": "openrct2sg.scenery_wall.door",
        "name": "Door",
        "is_door": True,
        "animation": {
            "frames": [
                [{"mesh_index": 0, "position": [0, 0, 0], "orientation": [0, 22 * g, 0]}]
                for g in range(frames)
            ]
        },
        **overrides,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "dr.obj")])


def test_door_loads_five_poses_and_is_not_animated(tmp_path):
    obj = _make_door(tmp_path)
    assert obj.is_door
    assert obj.is_animated is False  # doors take their own paint path
    assert len(obj.model.meshes[0]) == 5


def test_door_wrong_frame_count_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_door(tmp_path, frames=4)


def test_door_without_animation_rejected(tmp_path):
    (tmp_path / "dr.obj").write_text("v 0 0 0\nv 0 0 1\nv 0 1 0\nf 1 2 3\n")
    from openrct2_x7_renderer.mesh import load_mesh

    with pytest.raises(LoadError):
        build_wall_scenery(
            {
                "id": "openrct2sg.scenery_wall.d",
                "name": "D",
                "is_door": True,
                "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
            },
            [load_mesh(tmp_path / "dr.obj")],
        )


def test_door_render_count_and_helper(tmp_path):
    from openrct2_scenery_generator.sprite_renderer import (
        count_wall_door_sprites,
        render_wall_door,
    )

    obj = _make_door(tmp_path)
    imgs = render_wall_door(_FakeContext(), obj.meshes, obj.model, obj.units_per_tile)
    assert len(imgs) == 36
    assert count_wall_door_sprites() == 36


def test_door_render_blank_when_empty_and_progress():
    from openrct2_scenery_generator.sprite_renderer import render_wall_door
    from openrct2_x7_renderer.types import MeshFrame, Model

    # 5 poses over one empty mesh: every group renders blank body slots (36 total)
    # and progress fires once per the 9 swing groups.
    model = Model(meshes=[[MeshFrame(mesh_index=0) for _ in range(5)]])
    calls: list[tuple[int, int]] = []
    imgs = render_wall_door(
        _FakeContext(), [_empty_mesh()], model, progress=lambda a, b: calls.append((a, b))
    )
    assert len(imgs) == 36
    assert len(calls) == 9


def test_door_leaf_face_mask_splits_moving_from_static():
    import numpy as _np
    from openrct2_scenery_generator.sprite_renderer import _door_leaf_face_mask

    m = _empty_mesh()

    def mesh(verts):
        return Mesh(
            vertices=_np.array(verts, dtype=_np.float32),
            normals=_np.array([[0, 0, 1]] * 4, dtype=_np.float32),
            uvs=_np.zeros((4, 2), dtype=_np.float32),
            # face 0 uses the static verts 0,1; face 1 uses the moving vert 3.
            faces=_np.array([[0, 1, 2], [1, 3, 2]], dtype=_np.uint32),
            face_materials=_np.zeros(2, dtype=_np.uint32),
            materials=m.materials,
        )

    closed = mesh([[0, 0, 0], [0, 1, 0], [0, 0, 0.5], [0, 1, 1]])
    opened = mesh([[0, 0, 0], [0, 1, 0], [0, 0, 0.5], [1, 1, 1]])  # only vert 3 moved
    mask = _door_leaf_face_mask(closed, opened)
    assert list(mask) == [False, True]  # face 0 static (frame), face 1 moving (leaf)


def test_door_leaf_face_mask_all_leaf_when_rigid():
    import numpy as _np
    from openrct2_scenery_generator.sprite_renderer import _door_leaf_face_mask

    m = _empty_mesh()
    verts = _np.array([[0, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=_np.float32)
    rigid = Mesh(
        vertices=verts, normals=_np.array([[0, 0, 1]] * 3, dtype=_np.float32),
        uvs=_np.zeros((3, 2), dtype=_np.float32),
        faces=_np.array([[0, 1, 2]], dtype=_np.uint32),
        face_materials=_np.zeros(1, dtype=_np.uint32), materials=m.materials,
    )
    # Identical closed/open -> nothing moves -> the whole door is treated as leaf.
    assert list(_door_leaf_face_mask(rigid, rigid)) == [True]


def test_moving_face_mask_unions_motion_across_all_frames():
    import numpy as _np
    from openrct2_scenery_generator.sprite_renderer import _moving_face_mask

    m = _empty_mesh()

    def mesh(verts):
        return Mesh(
            vertices=_np.array(verts, dtype=_np.float32),
            normals=_np.array([[0, 0, 1]] * 4, dtype=_np.float32),
            uvs=_np.zeros((4, 2), dtype=_np.float32),
            # face 0 uses the static verts 0,1,2; face 1 uses the moving vert 3.
            faces=_np.array([[0, 1, 2], [1, 3, 2]], dtype=_np.uint32),
            face_materials=_np.zeros(2, dtype=_np.uint32),
            materials=m.materials,
        )

    # Vert 3 moves only in the middle frame and returns to its start by the last
    # one, so a first-vs-last comparison would miss it; the union across frames
    # must still flag face 1 as moving.
    f0 = mesh([[0, 0, 0], [0, 1, 0], [0, 0, 0.5], [0, 1, 1]])
    f1 = mesh([[0, 0, 0], [0, 1, 0], [0, 0, 0.5], [1, 1, 1]])
    f2 = mesh([[0, 0, 0], [0, 1, 0], [0, 0, 0.5], [0, 1, 1]])
    assert list(_moving_face_mask([f0, f1, f2])) == [False, True]


def test_composite_over_aligns_offsets_and_crops():
    import numpy as _np
    from openrct2_scenery_generator.sprite_renderer import _composite_over

    # base spans screen box x:[0,2) y:[0,2); top spans x:[1,3) y:[1,3).
    base = IndexedImage(2, 2, 0, 0, _np.array([[5, 5], [5, 5]], dtype=_np.uint8))
    top = IndexedImage(2, 2, 1, 1, _np.array([[9, 7], [7, 0]], dtype=_np.uint8))
    out = _composite_over(base, top)
    # Union box is x:[0,3) y:[0,3); top paints over base where opaque (the 9 wins
    # the overlap cell), transparent index 0 leaves base showing through.
    assert (out.x_offset, out.y_offset, out.width, out.height) == (0, 0, 3, 3)
    assert out.pixels.tolist() == [[5, 5, 0], [5, 9, 7], [0, 7, 0]]


def test_render_wall_door_topology_change_falls_back_to_whole_leaf():
    import numpy as _np
    from openrct2_scenery_generator.sprite_renderer import render_wall_door
    from openrct2_x7_renderer.types import MeshFrame, Model

    # Pose meshes with different vertex/face counts (per-pose re-extracted
    # deforming geometry): the vertex-motion leaf split is undefined, so the
    # whole pose renders as the leaf and the table still fills 36 slots.
    v = _np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=_np.float32)
    tri = Mesh(
        vertices=v, normals=v.copy(),
        uvs=_np.zeros((3, 2), dtype=_np.float32),
        faces=_np.array([[0, 1, 2]], dtype=_np.uint32),
        face_materials=_np.zeros(1, dtype=_np.uint32),
        materials=[Material()],
    )
    quad = _back_front_mesh()  # 4 vertices / 2 faces
    model = Model(meshes=[[MeshFrame(mesh_index=0)] + [MeshFrame(mesh_index=1)] * 4])
    imgs = render_wall_door(_FakeContext(), [tri, quad], model)
    assert len(imgs) == 36


def test_render_wall_animated_blank_frames_and_progress():
    from openrct2_scenery_generator.sprite_renderer import render_wall_animated
    from openrct2_x7_renderer.types import MeshFrame, Model

    # One model entry pointing at an empty mesh across all 8 frames: every frame's
    # combined mesh is empty, so each emits two blank placeholders (16 total) and
    # the progress callback still fires once per frame.
    model = Model(meshes=[[MeshFrame(mesh_index=0) for _ in range(8)]])
    calls: list[tuple[int, int]] = []
    imgs = render_wall_animated(
        _FakeContext(), [_empty_mesh()], model, progress=lambda a, b: calls.append((a, b))
    )
    assert len(imgs) == 16
    assert len(calls) == 8


def test_animated_wall_json_drops_slope_glass(tmp_path, caplog):
    # An animated wall authored with slope/glass must emit a flat-only flag set.
    obj = _make_animated_wall(tmp_path, is_allowed_on_slope=True, has_glass=True)
    with caplog.at_level("WARNING"):
        props = build_wall_scenery_json(obj)["properties"]
    assert props.get("isAnimated") is True
    assert "isAllowedOnSlope" not in props
    assert "hasGlass" not in props
    assert "flat-only" in caplog.text


def _make_large(tmp_path, ntiles=2, **overrides):
    from openrct2_x7_renderer.mesh import load_mesh

    (tmp_path / "m.obj").write_text(
        "v 0 0 0\nv 0.2 0 0\nv 0 1 0\n"
        "v 3.3 0 0\nv 3.5 0 0\nv 3.3 1 0\n"
        "f 1 2 3\nf 4 5 6\n"
    )
    tiles = [{"x": i, "y": 0, "z": 0, "clearance": 40} for i in range(ntiles)]
    config = {
        "id": "openrct2sg.scenery_large.test",
        "name": "Test Gate",
        "object_type": "scenery_large",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": tiles,
        **overrides,
    }
    mesh = load_mesh(tmp_path / "m.obj")
    return build_large_scenery(config, [mesh])


def test_large_json_shape(tmp_path):
    obj = _make_large(tmp_path, ntiles=2, price=8.0, has_primary_colour=True)
    j = build_large_scenery_json(obj)
    assert j["objectType"] == "scenery_large"
    props = j["properties"]
    assert len(props["tiles"]) == 2
    assert props["tiles"][1]["x"] == -32
    assert props["tiles"][0]["corners"] == 0xF
    assert props["hasPrimaryColour"] is True


def test_large_render_order_and_count(tmp_path):
    obj = _make_large(tmp_path, ntiles=2)
    combined = combine_model_world(obj.meshes, obj.model)
    import numpy as np

    centers = np.array([[0.0, 0.0], [3.3, 0.0]])
    imgs = render_large_scenery(_FakeContext(), combined, centers)
    assert len(imgs) == count_large_scenery_sprites(2) == 12


from openrct2_scenery_generator.sprite_renderer import (  # noqa: E402
    _render_4_rotations,
    _render_wall_block,
    _render_wall_view,
)
from openrct2_scenery_generator.types import SmallScenery  # noqa: E402
from openrct2_x7_renderer.mesh import Material, Mesh  # noqa: E402


def _empty_mesh() -> Mesh:
    """A Mesh with no faces (but valid vertex/normal/uv arrays)."""
    v = np.zeros((3, 3), dtype=np.float32)
    return Mesh(
        vertices=v,
        normals=v.copy(),
        uvs=np.zeros((3, 2), dtype=np.float32),
        faces=np.zeros((0, 3), dtype=np.uint32),
        face_materials=np.zeros(0, dtype=np.uint32),
        materials=[Material()],
    )


def test_render_wall_block_empty_mesh_returns_blanks_flat():
    blanks = _render_wall_block(None, _empty_mesh(), slope=False, views=(3, 0))
    assert len(blanks) == 2
    assert all(img.width == 1 for img in blanks)


def test_render_wall_block_empty_mesh_returns_blanks_slope():
    blanks = _render_wall_block(None, _empty_mesh(), slope=True, views=(3, 0))
    assert len(blanks) == 6


def test_render_wall_view_renders_each_cardinal_view():
    imgs = [_render_wall_view(_FakeContext(), _back_front_mesh(), v, 3.3) for v in range(4)]
    assert len(imgs) == 4


def test_render_small_scenery_anchored_empty_mesh_and_progress():
    from openrct2_scenery_generator.sprite_renderer import render_small_scenery_anchored

    blanks = render_small_scenery_anchored(None, _empty_mesh(), anchor=3.0)
    assert len(blanks) == 4
    assert all(img.width == 1 for img in blanks)

    calls: list[tuple[int, int]] = []
    imgs = render_small_scenery_anchored(
        _FakeContext(), _back_front_mesh(), 3.0, progress=lambda a, b: calls.append((a, b))
    )
    assert len(imgs) == 4
    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_render_4_rotations_empty_mesh_returns_blanks():
    blanks = _render_4_rotations(None, _empty_mesh(), cx=0.0, cz=0.0)
    assert len(blanks) == 4
    assert all(img.width == 1 for img in blanks)


def test_num_pose_groups_returns_one_when_not_animated():
    obj = SmallScenery()
    obj.is_animated = False
    assert obj.num_pose_groups == 1


def test_num_pose_groups_returns_one_when_frame_offsets_empty():
    obj = SmallScenery()
    obj.is_animated = True
    obj.frame_offsets = []
    assert obj.num_pose_groups == 1


from openrct2_scenery_generator.sprite_renderer import (  # noqa: E402
    count_path_addition_sprites,
    render_banner,
    render_path_addition,
)


def _back_front_mesh() -> Mesh:
    v = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 0, 2]], dtype=np.float32)
    back = Material()
    back.is_back = True
    return Mesh(
        vertices=v,
        normals=v.copy(),
        uvs=np.zeros((4, 2), dtype=np.float32),
        faces=np.array([[0, 1, 2], [1, 3, 2]], dtype=np.uint32),
        face_materials=np.array([0, 1], dtype=np.uint32),
        materials=[back, Material()],
    )


def test_render_banner_emits_eight_sprites():
    imgs = render_banner(_FakeContext(), _back_front_mesh())
    assert len(imgs) == 8


def test_render_banner_empty_layers_are_blank():
    imgs = render_banner(_FakeContext(), _empty_mesh())
    assert len(imgs) == 8
    assert all(img.width == 1 for img in imgs)


@pytest.mark.parametrize(
    ("render_as", "breakable", "n"),
    [("lamp", False, 5), ("lamp", True, 9), ("bench", True, 9), ("bin", False, 13),
     ("fountain", False, 5)],
)
def test_count_path_addition_sprites(render_as, breakable, n):
    assert count_path_addition_sprites(render_as, breakable=breakable) == n


def test_render_path_addition_count_matches_count_helper():
    tri = _back_front_mesh()
    for render_as, breakable in [("lamp", False), ("bench", True), ("fountain", False)]:
        imgs = render_path_addition(
            _FakeContext(), tri, None, None, render_as=render_as, breakable=breakable
        )
        assert len(imgs) == count_path_addition_sprites(render_as, breakable=breakable)


def test_render_path_addition_bin_uses_broken_and_full_meshes():
    tri = _back_front_mesh()
    imgs = render_path_addition(
        _FakeContext(), tri, tri, tri, render_as="bin", breakable=True
    )
    assert len(imgs) == 13


def test_render_path_addition_blank_preview_when_empty():
    imgs = render_path_addition(
        _FakeContext(), _empty_mesh(), None, None, render_as="lamp", breakable=False
    )
    assert len(imgs) == 5
    assert imgs[0].width == 1


def test_render_banner_and_path_addition_report_progress():
    calls: list[tuple[int, int]] = []
    render_banner(_FakeContext(), _back_front_mesh(), progress=lambda i, n: calls.append((i, n)))
    assert calls[-1] == (4, 4)
    calls.clear()
    render_path_addition(
        _FakeContext(), _back_front_mesh(), None, None,
        render_as="bin", breakable=True, progress=lambda i, n: calls.append((i, n)),
    )
    assert calls[-1] == (3, 3)


def _topology_mesh(n_faces):
    """A mesh with ``n_faces`` triangles (n_faces + 2 vertices)."""
    nv = n_faces + 2
    return Mesh(
        vertices=np.zeros((nv, 3), dtype=np.float32),
        normals=np.zeros((nv, 3), dtype=np.float32),
        uvs=np.zeros((nv, 2), dtype=np.float32),
        faces=np.array([[0, 1, 2]] * n_faces, dtype=np.uint32),
        face_materials=np.zeros(n_faces, dtype=np.uint32),
        materials=[Material()],
    )


def test_animated_unstable_topology_renders_whole_mesh_per_frame():
    from openrct2_scenery_generator.sprite_renderer import render_small_scenery_animated
    from openrct2_x7_renderer.types import MeshFrame, Model

    # Frame 0 has 1 face, frame 1 has 2: differing topology defeats the static/
    # moving split, so the whole mesh is rendered per frame (the fallback path).
    meshes = [_topology_mesh(1), _topology_mesh(2)]
    model = Model(meshes=[[MeshFrame(mesh_index=0), MeshFrame(mesh_index=1)]])
    calls: list[tuple[int, int]] = []
    imgs = render_small_scenery_animated(
        _FakeContext(), meshes, model, 2, progress=lambda a, b: calls.append((a, b))
    )
    # base (4 rotations) + a second copy (4) + one extra pose group (4) = 12.
    assert len(imgs) == 12
    # Progress fires once per pose group.
    assert calls == [(1, 2), (2, 2)]
