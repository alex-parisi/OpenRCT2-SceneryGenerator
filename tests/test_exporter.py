"""
Tests for images.dat emission, object.json assembly, and .parkobj zipping
across all scenery kinds.
"""

import json
import zipfile

import numpy as np
import pytest
from openrct2_object_common.parkobj import combine_indexed_images
from openrct2_object_common.testing import FakeContext
from openrct2_scenery_generator.exporter import (
    export_large_scenery,
    export_large_scenery_test,
    export_large_scenery_to,
    export_small_scenery,
    export_small_scenery_test,
    export_small_scenery_to,
    export_wall_scenery,
    export_wall_scenery_test,
    export_wall_scenery_to,
)
from openrct2_scenery_generator.loader import (
    build_large_scenery,
    build_small_scenery,
    build_wall_scenery,
)
from openrct2_x7_renderer.mesh import load_mesh
from openrct2_x7_renderer.types import IndexedImage

_TRI = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def _small(tmp_path, **overrides):
    (tmp_path / "m.obj").write_text(_TRI)
    config = {
        "id": "openrct2sg.scenery_small.test",
        "name": "Test",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "shape": "4/4",
        **overrides,
    }
    return build_small_scenery(config, [load_mesh(tmp_path / "m.obj")])


def _animated(tmp_path, poses=3, **overrides):
    (tmp_path / "m.obj").write_text(_TRI)
    offsets = list(range(poses)) + list(range(poses - 2, 0, -1))
    config = {
        "id": "openrct2sg.scenery_small.anim",
        "name": "Anim",
        "shape": "4/4",
        "animation": {
            "delay": 1,
            "mask": 7,
            "frame_offsets": offsets,
            "frames": [
                [{"mesh_index": 0, "position": [0, 0, 0], "orientation": [0, 90 * g, 0]}]
                for g in range(poses)
            ],
        },
        **overrides,
    }
    return build_small_scenery(config, [load_mesh(tmp_path / "m.obj")])


def _large(tmp_path, ntiles=2, **overrides):
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
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": tiles,
        **overrides,
    }
    return build_large_scenery(config, [load_mesh(tmp_path / "m.obj")])


def _wall(tmp_path, **overrides):
    (tmp_path / "wall.mtl").write_text(
        "newmtl Frame\nKd 0.5 0.5 0.5\nnewmtl Glass\nKd 0.2 0.2 0.8\n"
    )
    (tmp_path / "w.obj").write_text(
        "mtllib wall.mtl\n"
        "v 0 0 0\nv 0 0 1\nv 0 1 0\nv 0 1 1\n"
        "usemtl Frame\nf 1 2 3\n"
        "usemtl Glass\nf 2 4 3\n"
    )
    config = {
        "id": "openrct2sg.scenery_wall.test",
        "name": "Test Wall",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        **overrides,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "w.obj")])


def test_export_small_scenery_to_writes_parkobj(tmp_path):
    obj = _small(tmp_path)
    ctx = FakeContext()
    parkobj = tmp_path / "out" / "s.parkobj"
    work = tmp_path / "work"

    export_small_scenery_to(obj, ctx, parkobj, work)

    assert parkobj.exists()
    with zipfile.ZipFile(parkobj) as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..3]"]
    assert j["objectType"] == "scenery_small"
    assert "begin" in ctx.events and "finalize" in ctx.events
    assert any(isinstance(e, tuple) and e[0] == "add" for e in ctx.events)
    assert (work / "images.dat").exists()


def test_export_small_scenery_to_non_rotatable_single_sprite(tmp_path):
    obj = _small(tmp_path, is_rotatable=False)
    export_small_scenery_to(obj, FakeContext(), tmp_path / "s.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "s.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..0]"]


def test_export_small_scenery_to_half_tile_uses_anchored_path(tmp_path):
    # "2/4" objects paint from the {3,3} anchor, so each rotation renders in
    # its own translated scene rather than one shared scene.
    obj = _small(tmp_path, shape="2/4")
    ctx = FakeContext()
    export_small_scenery_to(obj, ctx, tmp_path / "h.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "h.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..3]"]
    assert sum(1 for e in ctx.events if e == "begin") == 4


def test_export_small_scenery_voffset_centre_flag_and_anchor(tmp_path):
    obj = _small(tmp_path, shape="4/4+D", voffset_centre=True, prohibit_walls=True)
    ctx = FakeContext()
    export_small_scenery_to(obj, ctx, tmp_path / "d.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "d.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["properties"]["SMALL_SCENERY_FLAG_VOFFSET_CENTRE"] is True
    assert j["properties"]["prohibitWalls"] is True
    assert sum(1 for e in ctx.events if e == "begin") == 4


def test_export_small_scenery_test_half_tile_writes_rotation_pngs(tmp_path):
    obj = _small(tmp_path, shape="2/4")
    test_dir = tmp_path / "test"
    export_small_scenery_test(obj, FakeContext(), test_dir)
    for i in range(4):
        assert (test_dir / f"scenery_{i}.png").exists()
    assert (test_dir / "preview_combined.png").exists()


def test_export_small_scenery_animated_half_tile_anchors_each_direction(tmp_path):
    obj = _animated(tmp_path, poses=3, shape="2/4")
    test_dir = tmp_path / "test"
    export_small_scenery_test(obj, FakeContext(), test_dir)
    for d in range(4):
        assert (test_dir / f"base_{d}.png").exists()


def test_export_small_scenery_to_animated_emits_group_block(tmp_path):
    obj = _animated(tmp_path, poses=3)
    export_small_scenery_to(obj, FakeContext(), tmp_path / "a.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "a.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..15]"]
    assert j["properties"]["isAnimated"] is True


def test_export_small_scenery_to_skip_render_reuses_images(tmp_path):
    obj = _small(tmp_path)
    work = tmp_path / "work"
    export_small_scenery_to(obj, FakeContext(), tmp_path / "first.parkobj", work)

    ctx2 = FakeContext()
    export_small_scenery_to(obj, ctx2, tmp_path / "second.parkobj", work, skip_render=True)
    assert ctx2.events == []

    with zipfile.ZipFile(tmp_path / "second.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..3]"]


def test_export_small_scenery_to_skip_render_rejects_non_array_images(tmp_path):
    obj = _small(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "object.json").write_text(json.dumps({"images": "not-an-array"}))
    with pytest.raises(RuntimeError, match="images"):
        export_small_scenery_to(
            obj, FakeContext(), tmp_path / "x.parkobj", work, skip_render=True
        )


def test_export_small_scenery_wrapper_names_by_id(tmp_path, monkeypatch):
    obj = _small(tmp_path)
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "dist"

    export_small_scenery(obj, FakeContext(), out_dir)
    assert (out_dir / "openrct2sg.scenery_small.test.parkobj").exists()


def test_export_small_scenery_test_writes_one_png_per_rotation(tmp_path):
    obj = _small(tmp_path)
    test_dir = tmp_path / "test"
    export_small_scenery_test(obj, FakeContext(), test_dir)
    for i in range(4):
        assert (test_dir / f"scenery_{i}.png").exists()


def test_export_small_scenery_test_animated_writes_base_and_pose_pngs(tmp_path):
    obj = _animated(tmp_path, poses=3)
    test_dir = tmp_path / "test"
    export_small_scenery_test(obj, FakeContext(), test_dir)
    for d in range(4):
        assert (test_dir / f"base_{d}.png").exists()
    for g in range(3):
        for d in range(4):
            assert (test_dir / f"pose{g}_{d}.png").exists()


def test_export_small_scenery_test_writes_combined_preview(tmp_path):
    from openrct2_x7_renderer.image import read_png

    obj = _small(tmp_path)
    test_dir = tmp_path / "test"
    export_small_scenery_test(obj, FakeContext(), test_dir)
    img = read_png(test_dir / "preview_combined.png")
    assert (img.width, img.height) == (2, 2)


def test_export_large_scenery_test_writes_combined_preview(tmp_path):
    from openrct2_x7_renderer.image import read_png

    obj = _large(tmp_path, ntiles=2)
    test_dir = tmp_path / "test"
    export_large_scenery_test(obj, FakeContext(), test_dir)
    img = read_png(test_dir / "preview_combined.png")
    assert (img.width, img.height) == (2, 2)


def test_combine_indexed_images_grid_layout():
    imgs = [
        IndexedImage(1, 1, 0, 0, np.full((1, 1), v, dtype=np.uint8))
        for v in (10, 20, 30, 40)
    ]
    out = combine_indexed_images(imgs, columns=2)
    assert (out.width, out.height) == (2, 2)
    assert out.pixels.tolist() == [[10, 20], [30, 40]]


def test_combine_indexed_images_single_image_no_blank_cell():
    one = IndexedImage(1, 1, 0, 0, np.full((1, 1), 7, dtype=np.uint8))
    out = combine_indexed_images([one], columns=2)
    assert (out.width, out.height) == (1, 1)


def test_export_large_scenery_to_writes_parkobj(tmp_path):
    obj = _large(tmp_path, ntiles=2)
    export_large_scenery_to(obj, FakeContext(), tmp_path / "g.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "g.parkobj") as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..11]"]
    assert j["objectType"] == "scenery_large"


def test_export_large_scenery_wrapper_names_by_id(tmp_path, monkeypatch):
    obj = _large(tmp_path)
    monkeypatch.chdir(tmp_path)
    export_large_scenery(obj, FakeContext(), tmp_path / "dist")
    assert (tmp_path / "dist" / "openrct2sg.scenery_large.test.parkobj").exists()


def test_export_large_scenery_test_writes_preview_and_tile_pngs(tmp_path):
    obj = _large(tmp_path, ntiles=2)
    test_dir = tmp_path / "test"
    export_large_scenery_test(obj, FakeContext(), test_dir)
    for d in range(4):
        assert (test_dir / f"preview_{d}.png").exists()
    for seq in range(2):
        for d in range(4):
            assert (test_dir / f"tile{seq}_{d}.png").exists()


def test_export_wall_scenery_to_writes_parkobj(tmp_path):
    obj = _wall(tmp_path)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..1]"]
    assert j["objectType"] == "scenery_wall"


def test_export_wall_scenery_to_glass_emits_twelve(tmp_path):
    obj = _wall(tmp_path, has_glass=True)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..11]"]


def test_export_wall_scenery_wrapper_names_by_id(tmp_path, monkeypatch):
    obj = _wall(tmp_path)
    monkeypatch.chdir(tmp_path)
    export_wall_scenery(obj, FakeContext(), tmp_path / "dist")
    assert (tmp_path / "dist" / "openrct2sg.scenery_wall.test.parkobj").exists()


def _animated_wall(tmp_path, **overrides):
    (tmp_path / "aw.obj").write_text(_TRI)
    config = {
        "id": "openrct2sg.scenery_wall.anim",
        "name": "Anim Wall",
        "animation": {
            "frames": [[{"mesh_index": 0, "position": [0, 0, 0]}] for _ in range(8)]
        },
        **overrides,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "aw.obj")])


def test_export_animated_wall_emits_sixteen_frames(tmp_path):
    obj = _animated_wall(tmp_path)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..15]"]
    assert j["properties"].get("isAnimated") is True


def _door(tmp_path, **overrides):
    (tmp_path / "dr.obj").write_text(_TRI)
    config = {
        "id": "openrct2sg.scenery_wall.door",
        "name": "Door",
        "is_door": True,
        "animation": {
            "frames": [[{"mesh_index": 0, "position": [0, 0, 0]}] for _ in range(5)]
        },
        **overrides,
    }
    return build_wall_scenery(config, [load_mesh(tmp_path / "dr.obj")])


def test_export_door_wall_emits_thirty_six_images(tmp_path):
    obj = _door(tmp_path)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..35]"]
    assert j["properties"].get("isDoor") is True


def test_export_wall_scenery_test_writes_a_png_per_sprite(tmp_path):
    obj = _wall(tmp_path)
    test_dir = tmp_path / "test"
    export_wall_scenery_test(obj, FakeContext(), test_dir)
    assert (test_dir / "wall_0.png").exists()
    assert (test_dir / "wall_1.png").exists()


def test_export_wall_scenery_test_writes_combined_preview(tmp_path):
    from openrct2_x7_renderer.image import read_png

    obj = _wall(tmp_path)
    test_dir = tmp_path / "test"
    export_wall_scenery_test(obj, FakeContext(), test_dir)
    img = read_png(test_dir / "preview_combined.png")
    assert (img.width, img.height) == (2, 1)


def test_export_small_scenery_to_reports_progress(tmp_path):
    obj = _small(tmp_path)
    calls: list[tuple[int, int]] = []
    export_small_scenery_to(
        obj, FakeContext(), tmp_path / "s.parkobj", tmp_path / "w",
        progress=lambda d, t: calls.append((d, t)),
    )
    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_export_small_scenery_to_reports_progress_animated(tmp_path):
    obj = _animated(tmp_path, poses=3)
    calls: list[tuple[int, int]] = []
    export_small_scenery_to(
        obj, FakeContext(), tmp_path / "a.parkobj", tmp_path / "w",
        progress=lambda d, t: calls.append((d, t)),
    )
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_export_large_scenery_to_reports_progress(tmp_path):
    obj = _large(tmp_path, ntiles=2)
    calls: list[tuple[int, int]] = []
    export_large_scenery_to(
        obj, FakeContext(), tmp_path / "g.parkobj", tmp_path / "w",
        progress=lambda d, t: calls.append((d, t)),
    )
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_export_wall_scenery_to_reports_progress(tmp_path):
    obj = _wall(tmp_path)
    calls: list[tuple[int, int]] = []
    export_wall_scenery_to(
        obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w",
        progress=lambda d, t: calls.append((d, t)),
    )
    assert calls == [(1, 1)]


def test_combine_indexed_images_empty_returns_blank():
    out = combine_indexed_images([])
    assert out.width == 1
    assert out.height == 1


def test_build_small_scenery_json_includes_scenery_group(tmp_path):
    from openrct2_scenery_generator.exporter import build_small_scenery_json

    obj = _small(tmp_path, scenery_group="rct2.scenery_group.mygroup")
    j = build_small_scenery_json(obj)
    assert j["properties"]["sceneryGroup"] == "rct2.scenery_group.mygroup"


def test_build_large_scenery_json_includes_scrolling_mode_and_scenery_group(tmp_path):
    from openrct2_scenery_generator.exporter import build_large_scenery_json
    from openrct2_scenery_generator.loader import build_large_scenery

    config = {
        "id": "openrct2sg.scenery_large.sign",
        "name": "Sign",
        "object_type": "scenery_large",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": [{"x": 0, "y": 0}],
        "scrolling_mode": 2,
        "scenery_group": "rct2.scenery_group.signs",
    }
    (tmp_path / "m.obj").write_text(_TRI)
    from openrct2_x7_renderer.mesh import load_mesh

    obj = build_large_scenery(config, [load_mesh(tmp_path / "m.obj")])
    j = build_large_scenery_json(obj)
    assert j["properties"]["scrollingMode"] == 2
    assert j["properties"]["sceneryGroup"] == "rct2.scenery_group.signs"


def test_build_wall_scenery_json_includes_scenery_group(tmp_path):
    from openrct2_scenery_generator.exporter import build_wall_scenery_json

    obj = _wall(tmp_path, scenery_group="rct2.scenery_group.walls")
    j = build_wall_scenery_json(obj)
    assert j["properties"]["sceneryGroup"] == "rct2.scenery_group.walls"


def _banner(tmp_path, **overrides):
    (tmp_path / "b.mtl").write_text(
        "newmtl PostBack\nKd 0.3 0.2 0.1\nnewmtl Post\nKd 0.3 0.2 0.1\n"
    )
    (tmp_path / "b.obj").write_text(
        "mtllib b.mtl\n"
        "v 0 0 -1\nv 0 0 -0.8\nv 0 1 -1\n"
        "v 0 0 1\nv 0 0 0.8\nv 0 1 1\n"
        "usemtl PostBack\nf 1 2 3\n"
        "usemtl Post\nf 4 5 6\n"
    )
    config = {
        "id": "openrct2sg.footpath_banner.test",
        "name": "Test Banner",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        **overrides,
    }
    from openrct2_scenery_generator.loader import build_banner

    return build_banner(config, [load_mesh(tmp_path / "b.obj")])


def test_export_banner_to_writes_eight_sprites(tmp_path):
    from openrct2_scenery_generator.exporter import export_banner_to

    obj = _banner(tmp_path, price=250, has_primary_colour=True, scrolling_mode=17)
    parkobj = tmp_path / "b.parkobj"
    export_banner_to(obj, FakeContext(), parkobj, tmp_path / "w")
    with zipfile.ZipFile(parkobj) as zf:
        j = json.loads(zf.read("object.json"))
    assert j["objectType"] == "footpath_banner"
    assert j["images"] == ["$LGX:images.dat[0..7]"]
    assert j["properties"]["hasPrimaryColour"] is True
    assert j["properties"]["scrollingMode"] == 17


def test_build_banner_json_omits_unset(tmp_path):
    from openrct2_scenery_generator.exporter import build_banner_json

    j = build_banner_json(_banner(tmp_path))
    assert "hasPrimaryColour" not in j["properties"]
    assert "scrollingMode" not in j["properties"]


def test_build_banner_json_includes_scenery_group(tmp_path):
    from openrct2_scenery_generator.exporter import build_banner_json

    j = build_banner_json(_banner(tmp_path, scenery_group="grp.id"))
    assert j["properties"]["sceneryGroup"] == "grp.id"


def _item(tmp_path, **overrides):
    (tmp_path / "m.obj").write_text(_TRI)
    config = {
        "id": "openrct2sg.footpath_item.test",
        "name": "Test Item",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        **overrides,
    }
    from openrct2_scenery_generator.loader import build_path_addition

    return build_path_addition(config, [load_mesh(tmp_path / "m.obj")])


@pytest.mark.parametrize(
    ("render_as", "breakable", "n"),
    [("lamp", False, 5), ("bench", True, 9), ("bin", False, 13), ("fountain", False, 5)],
)
def test_export_path_addition_image_counts(tmp_path, render_as, breakable, n):
    from openrct2_scenery_generator.exporter import export_path_addition_to

    obj = _item(tmp_path, render_as=render_as, is_breakable=breakable)
    parkobj = tmp_path / f"{render_as}.parkobj"
    export_path_addition_to(obj, FakeContext(), parkobj, tmp_path / f"w_{render_as}")
    with zipfile.ZipFile(parkobj) as zf:
        j = json.loads(zf.read("object.json"))
    assert j["objectType"] == "footpath_item"
    assert j["images"] == [f"$LGX:images.dat[0..{n - 1}]"]


def test_build_path_addition_json_flags(tmp_path):
    from openrct2_scenery_generator.exporter import build_path_addition_json

    obj = _item(tmp_path, render_as="bench", is_breakable=True, is_allowed_on_queue=False)
    props = build_path_addition_json(obj)["properties"]
    assert props["renderAs"] == "bench"
    assert props["isBench"] is True
    assert props["isBreakable"] is True
    assert props["isAllowedOnSlope"] is True
    assert "isAllowedOnQueue" not in props


def test_build_path_addition_json_drops_breakable_fountain(tmp_path, caplog):
    from openrct2_scenery_generator.exporter import build_path_addition_json

    obj = _item(tmp_path, render_as="fountain", is_breakable=True)
    with caplog.at_level("WARNING"):
        props = build_path_addition_json(obj)["properties"]
    assert "isBreakable" not in props
    assert "no broken sprites" in caplog.text


def test_build_path_addition_json_includes_scenery_group(tmp_path):
    from openrct2_scenery_generator.exporter import build_path_addition_json

    obj = _item(tmp_path, render_as="lamp", scenery_group="grp.id")
    assert build_path_addition_json(obj)["properties"]["sceneryGroup"] == "grp.id"


def test_path_addition_missing_broken_mesh_still_full_count(tmp_path):
    from openrct2_scenery_generator.exporter import export_path_addition_to

    obj = _item(tmp_path, render_as="bench", is_breakable=True)
    assert not obj.broken_meshes
    export_path_addition_to(obj, FakeContext(), tmp_path / "b.parkobj", tmp_path / "wb")
    with zipfile.ZipFile(tmp_path / "b.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..8]"]


def test_export_scenery_group_writes_two_icons_without_render(tmp_path):
    from openrct2_scenery_generator.exporter import export_scenery_group_to
    from openrct2_scenery_generator.loader import build_scenery_group

    obj = build_scenery_group(
        {
            "id": "openrct2sg.scenery_group.test",
            "name": "Group",
            "priority": 7,
            "entries": ["a.b.c", "d.e.f"],
        },
        IndexedImage.blank(4, 4),
    )
    ctx = FakeContext()
    parkobj = tmp_path / "g.parkobj"
    export_scenery_group_to(obj, ctx, parkobj, tmp_path / "wg")
    with zipfile.ZipFile(parkobj) as zf:
        j = json.loads(zf.read("object.json"))
    assert j["objectType"] == "scenery_group"
    assert j["images"] == ["$LGX:images.dat[0..1]"]
    assert j["properties"] == {"priority": 7, "entries": ["a.b.c", "d.e.f"]}
    assert ctx.events == []


def _group(entries=("a.b.c",), preview=None):
    from openrct2_scenery_generator.loader import build_scenery_group

    return build_scenery_group(
        {"id": "openrct2sg.scenery_group.t", "name": "G", "entries": list(entries)},
        preview,
    )


def test_export_new_type_dir_wrappers(tmp_path, monkeypatch):
    from openrct2_scenery_generator.exporter import (
        export_banner,
        export_path_addition,
        export_scenery_group,
    )

    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "dist"
    export_banner(_banner(tmp_path), FakeContext(), out_dir)
    export_path_addition(_item(tmp_path, render_as="lamp"), FakeContext(), out_dir)
    export_scenery_group(_group(), FakeContext(), out_dir)
    assert (out_dir / "openrct2sg.footpath_banner.test.parkobj").exists()
    assert (out_dir / "openrct2sg.footpath_item.test.parkobj").exists()
    assert (out_dir / "openrct2sg.scenery_group.t.parkobj").exists()


def test_export_banner_test_writes_pngs(tmp_path):
    from openrct2_scenery_generator.exporter import export_banner_test

    test_dir = tmp_path / "test"
    export_banner_test(_banner(tmp_path), FakeContext(), test_dir)
    for d in range(4):
        assert (test_dir / f"banner_{d}_back.png").exists()
        assert (test_dir / f"banner_{d}_front.png").exists()


def test_export_path_addition_test_writes_pngs(tmp_path):
    from openrct2_scenery_generator.exporter import export_path_addition_test

    test_dir = tmp_path / "test"
    obj = _item(tmp_path, render_as="bin")
    export_path_addition_test(obj, FakeContext(), test_dir)
    assert (test_dir / "preview.png").exists()
    for i in range(1, 13):
        assert (test_dir / f"item_{i}.png").exists()


def test_export_scenery_group_test_writes_icon(tmp_path):
    from openrct2_scenery_generator.exporter import export_scenery_group_test

    test_dir = tmp_path / "test"
    export_scenery_group_test(_group(preview=IndexedImage.blank(4, 4)), FakeContext(), test_dir)
    assert (test_dir / "icon.png").exists()


def test_export_scenery_group_reports_progress(tmp_path):
    from openrct2_scenery_generator.exporter import export_scenery_group_to

    calls: list[tuple[int, int]] = []
    export_scenery_group_to(
        _group(), FakeContext(), tmp_path / "g.parkobj", tmp_path / "wg",
        progress=lambda i, n: calls.append((i, n)),
    )
    assert calls == [(1, 1)]
