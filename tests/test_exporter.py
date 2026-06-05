"""Tests for images.dat emission, object.json assembly, and .parkobj zipping
across all three scenery kinds.

The native ray tracer is stubbed via a fake render context that mirrors the
renderer's begin_render -> SceneBuilder -> FinalizedScene flow: every view
renders a 1x1 dummy and the lifecycle (begin/add/finalize/end) is recorded.
Everything downstream of the pixels -- write_images_dat, write_png, the zip --
runs for real against tmp_path. The build_*_json shapes are covered by
test_scenery / test_scenery_loader; this file owns the export/file-writing path.
"""

import json
import zipfile

import numpy as np
import pytest
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


def _img() -> IndexedImage:
    return IndexedImage(1, 1, 0, 0, np.zeros((1, 1), dtype=np.uint8))


class FakeScene:
    """Stands in for a FinalizedScene; every view renders a 1x1 dummy."""

    def __init__(self, events):
        self._events = events

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def render_view(self, _view):
        return _img()

    def render_silhouette(self, _view):
        return _img()

    def end_render(self):
        self._events.append("end")


class FakeBuilder:
    """Stands in for a SceneBuilder, recording add_model/finalize calls."""

    def __init__(self, events):
        self._events = events

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def add_model(self, *_a, **_k):
        self._events.append("add")
        return self

    def finalize(self):
        self._events.append("finalize")
        return FakeScene(self._events)


class FakeContext:
    """Records the render lifecycle calls without touching Embree."""

    def __init__(self):
        self.events = []

    def begin_render(self):
        self.events.append("begin")
        return FakeBuilder(self.events)


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
    # Two triangles, one near OBJ X=0 and one near OBJ X=TILE_SIZE, so the
    # binner splits them across the two tiles.
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
    # One Frame face + one Glass face, so the glass splitter has a material to
    # classify by name.
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


# --------------------------------------------------------------------------
# Small scenery
# --------------------------------------------------------------------------


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
    # Rotatable -> 4 rotation sprites -> images[0..3].
    assert j["images"] == ["$LGX:images.dat[0..3]"]
    assert j["objectType"] == "scenery_small"
    # The static path opens a scene (begin), adds the model, and finalizes;
    # cleanup runs through the `with` block's __exit__, not an explicit end.
    assert "begin" in ctx.events and "add" in ctx.events and "finalize" in ctx.events
    assert (work / "images.dat").exists()


def test_export_small_scenery_to_non_rotatable_single_sprite(tmp_path):
    obj = _small(tmp_path, is_rotatable=False)
    export_small_scenery_to(obj, FakeContext(), tmp_path / "s.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "s.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    assert j["images"] == ["$LGX:images.dat[0..0]"]


def test_export_small_scenery_to_animated_emits_group_block(tmp_path):
    obj = _animated(tmp_path, poses=3)
    export_small_scenery_to(obj, FakeContext(), tmp_path / "a.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "a.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    # 4 base + 3 pose groups * 4 rotations = 16 -> images[0..15].
    assert j["images"] == ["$LGX:images.dat[0..15]"]
    assert j["properties"]["isAnimated"] is True


def test_export_small_scenery_to_skip_render_reuses_images(tmp_path):
    obj = _small(tmp_path)
    work = tmp_path / "work"
    export_small_scenery_to(obj, FakeContext(), tmp_path / "first.parkobj", work)

    ctx2 = FakeContext()
    export_small_scenery_to(obj, ctx2, tmp_path / "second.parkobj", work, skip_render=True)
    assert ctx2.events == []  # nothing rendered

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
    # export_small_scenery derives the filename from obj.id and writes into the
    # given output directory using a relative "object" work dir; run from
    # tmp_path to keep the repo clean.
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


# --------------------------------------------------------------------------
# Large scenery
# --------------------------------------------------------------------------


def test_export_large_scenery_to_writes_parkobj(tmp_path):
    obj = _large(tmp_path, ntiles=2)
    export_large_scenery_to(obj, FakeContext(), tmp_path / "g.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "g.parkobj") as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}
        j = json.loads(zf.read("object.json"))
    # 4 preview + 4 per tile * 2 tiles = 12 -> images[0..11].
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


# --------------------------------------------------------------------------
# Walls
# --------------------------------------------------------------------------


def test_export_wall_scenery_to_writes_parkobj(tmp_path):
    obj = _wall(tmp_path)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}
        j = json.loads(zf.read("object.json"))
    # Flat only (no slope/glass/double) -> 2 sprites -> images[0..1].
    assert j["images"] == ["$LGX:images.dat[0..1]"]
    assert j["objectType"] == "scenery_wall"


def test_export_wall_scenery_to_glass_emits_twelve(tmp_path):
    obj = _wall(tmp_path, has_glass=True)
    export_wall_scenery_to(obj, FakeContext(), tmp_path / "wall.parkobj", tmp_path / "w")
    with zipfile.ZipFile(tmp_path / "wall.parkobj") as zf:
        j = json.loads(zf.read("object.json"))
    # Glass forces the 6 body + 6 overlay block layout -> images[0..11].
    assert j["images"] == ["$LGX:images.dat[0..11]"]


def test_export_wall_scenery_wrapper_names_by_id(tmp_path, monkeypatch):
    obj = _wall(tmp_path)
    monkeypatch.chdir(tmp_path)
    export_wall_scenery(obj, FakeContext(), tmp_path / "dist")
    assert (tmp_path / "dist" / "openrct2sg.scenery_wall.test.parkobj").exists()


def test_export_wall_scenery_test_writes_a_png_per_sprite(tmp_path):
    obj = _wall(tmp_path)
    test_dir = tmp_path / "test"
    export_wall_scenery_test(obj, FakeContext(), test_dir)
    # Flat wall -> 2 sprites -> wall_0.png, wall_1.png.
    assert (test_dir / "wall_0.png").exists()
    assert (test_dir / "wall_1.png").exists()
