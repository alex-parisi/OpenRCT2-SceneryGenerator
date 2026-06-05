"""Tests for the small-scenery generator: sprite counts, render dispatch, and
object.json shape. The native renderer is stubbed so this runs without Embree."""

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


@pytest.mark.parametrize("rotatable,expected", [(True, 4), (False, 1)])
def test_count_matches_render(rotatable, expected):
    num = 4 if rotatable else 1
    assert count_small_scenery_sprites(num) == expected
    assert len(render_small_scenery(_FakeScene(), num_rotations=num)) == expected


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


def test_rotatable_defaults_true(tmp_path):
    obj = _make_scenery(tmp_path)
    assert obj.num_rotations == 4
    obj2 = _make_scenery(tmp_path, is_rotatable=False)
    assert obj2.num_rotations == 1


def test_bad_shape_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_scenery(tmp_path, shape="5/4")


# --- small scenery animation (frameOffsets path) ---


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
    # Each pose carries one MeshFrame for the single model entry.
    assert len(obj.model.meshes) == 1
    assert len(obj.model.meshes[0]) == 3
    # 4 base sprites + 3 groups * 4 rotations, regardless of is_rotatable.
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
    # Required to suppress the engine's static base-parent draw (the frozen
    # pose-0 ghost) and shift the animation index past the base group.
    assert props["SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED"] is True


def test_animated_render_order_and_count(tmp_path):
    from openrct2_scenery_generator.sprite_renderer import render_small_scenery_animated

    obj = _make_animated(tmp_path, poses=3)
    imgs = render_small_scenery_animated(
        _FakeContext(), obj.meshes, obj.model, obj.num_pose_groups
    )
    assert len(imgs) == 16  # 4 base + 3 groups * 4, group-major, direction-minor


def test_animated_frame_offset_pose_mismatch_rejected(tmp_path):
    # frame_offsets references pose 3 but only 2 poses are supplied.
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


# --- large scenery ---

from openrct2_scenery_generator.exporter import build_large_scenery_json  # noqa: E402
from openrct2_scenery_generator.loader import build_large_scenery  # noqa: E402
from openrct2_scenery_generator.sprite_renderer import (  # noqa: E402
    count_large_scenery_sprites,
    render_large_scenery,
)
from openrct2_x7_renderer.geometry import combine_model_world  # noqa: E402


@pytest.mark.parametrize("tiles,expected", [(1, 8), (2, 12), (4, 20)])
def test_large_count(tiles, expected):
    # 4 preview + 4 per tile.
    assert count_large_scenery_sprites(tiles) == expected


# --- walls ---

from openrct2_scenery_generator.exporter import build_wall_scenery_json  # noqa: E402
from openrct2_scenery_generator.loader import build_wall_scenery  # noqa: E402
from openrct2_scenery_generator.sprite_renderer import render_wall  # noqa: E402


def _make_wall(tmp_path, *, glass=False, **overrides):
    """A two-face wall mesh: one Frame face, one Glass face."""
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
    """A wall with a shared Frame face, a Front-only face, and a Back-only face."""
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
    # Frame=(F,F) shared, FrontPanel=(T,F), BackPanel=(F,T).
    assert by_side == {(False, False), (True, False), (False, True)}


def test_double_sided_blocks_exclude_opposite_side(tmp_path, monkeypatch):
    # The front block must drop Back faces and the back block must drop Front
    # faces (shared Frame survives both). Capture each block's face count.
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
    # Front block = Frame + FrontPanel = 2; back block = Frame + BackPanel = 2.
    assert seen == [2, 2]


def test_glass_double_combo_refused(tmp_path, capsys):
    # The +12 glass x double layout is unsupported: keep glass, drop double-sided.
    obj = _make_wall(tmp_path, glass=True, is_double_sided=True)
    props = build_wall_scenery_json(obj)["properties"]
    assert props.get("hasGlass") is True
    assert "isDoubleSided" not in props
    assert "combo is unsupported" in capsys.readouterr().out


def _make_large(tmp_path, ntiles=2, **overrides):
    from openrct2_x7_renderer.mesh import load_mesh

    # Two triangles, one near OBJ X=0, one near OBJ X=TILE_SIZE.
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
    # Config tile index 1 -> coordinate units (32 per tile), sign negated to
    # reconcile the renderer (+X up-right) with OpenRCT2 (+x lower-left).
    assert props["tiles"][1]["x"] == -32
    assert props["tiles"][0]["corners"] == 0xF
    assert props["hasPrimaryColour"] is True


def test_large_render_order_and_count(tmp_path):
    obj = _make_large(tmp_path, ntiles=2)
    combined = combine_model_world(obj.meshes, obj.model)
    import numpy as np

    centers = np.array([[0.0, 0.0], [3.3, 0.0]])
    imgs = render_large_scenery(_FakeContext(), combined, centers)
    # 4 preview + 4 per tile * 2 tiles.
    assert len(imgs) == count_large_scenery_sprites(2) == 12
