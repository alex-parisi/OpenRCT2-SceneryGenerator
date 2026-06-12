"""
Tests for shared scenery config validation, object-type dispatch, the
tile-centre mapping, and the wall/large object.json flag emission rules.
"""

import json

import numpy as np
import pytest
from openrct2_scenery_generator.constants import COORDS_PER_TILE
from openrct2_scenery_generator.exporter import (
    _tile_centers_xz,
    build_wall_scenery_json,
)
from openrct2_scenery_generator.loader import (
    LoadError,
    build_banner,
    build_large_scenery,
    build_path_addition,
    build_scenery_group,
    build_small_scenery,
    build_wall_scenery,
    load_large_scenery,
    load_scenery_group,
    load_small_scenery,
    load_wall_scenery,
    object_type_of,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.mesh import load_mesh


@pytest.fixture
def tri_mesh(tmp_path):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    return load_mesh(tmp_path / "m.obj")


def test_object_type_defaults_to_small():
    assert object_type_of({}) == "scenery_small"


@pytest.mark.parametrize(
    "t",
    [
        "scenery_small",
        "scenery_large",
        "scenery_wall",
        "footpath_banner",
        "footpath_item",
        "scenery_group",
    ],
)
def test_object_type_accepts_known_types(t):
    assert object_type_of({"object_type": t}) == t


def test_object_type_rejects_unknown():
    with pytest.raises(LoadError, match="Unrecognized object_type"):
        object_type_of({"object_type": "scenery_huge"})


def _wall_config(**overrides):
    base = {
        "id": "openrct2sg.scenery_wall.t",
        "name": "T",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    base.update(overrides)
    return base


def _door_frames(n=5):
    """A door `animation` block: n keyframed poses (closed + opening)."""
    return {"frames": [[{"mesh_index": 0, "position": [0, 0, 0]}] for _ in range(n)]}


@pytest.mark.parametrize("bad", [0, -4.0])
def test_units_per_tile_must_be_positive(tri_mesh, bad):
    with pytest.raises(LoadError, match="units_per_tile"):
        build_wall_scenery(_wall_config(units_per_tile=bad), [tri_mesh])


def test_units_per_tile_defaults_to_tile_size(tri_mesh):
    obj = build_wall_scenery(_wall_config(), [tri_mesh])
    assert obj.units_per_tile == TILE_SIZE


def _large_config(tiles, **overrides):
    base = {
        "id": "openrct2sg.scenery_large.t",
        "name": "T",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": tiles,
    }
    base.update(overrides)
    return base


def test_large_requires_non_empty_tiles(tri_mesh):
    with pytest.raises(LoadError, match="tiles"):
        build_large_scenery(_large_config([]), [tri_mesh])


def test_tile_centers_map_index_to_obj_units(tri_mesh):
    obj = build_large_scenery(
        _large_config([{"x": 0, "y": 0}, {"x": 1, "y": 2}]), [tri_mesh]
    )
    centers = _tile_centers_xz(obj)
    assert np.allclose(centers, [[0.0, 0.0], [TILE_SIZE, 2 * TILE_SIZE]])


def test_tile_centers_honour_render_scale(tri_mesh):
    obj = build_large_scenery(
        _large_config([{"x": 1, "y": 0}], units_per_tile=10.0), [tri_mesh]
    )
    assert np.allclose(_tile_centers_xz(obj), [[10.0, 0.0]])


def test_tile_centers_empty_when_no_tiles():
    from openrct2_scenery_generator.types import LargeScenery

    assert _tile_centers_xz(LargeScenery()).shape == (0, 2)


def test_wall_json_omits_unset_flags(tri_mesh):
    props = build_wall_scenery_json(build_wall_scenery(_wall_config(), [tri_mesh]))["properties"]
    for key in ("hasGlass", "isDoubleSided", "isAllowedOnSlope", "isDoor", "isOpaque"):
        assert key not in props
    assert "scrollingMode" not in props


def test_wall_json_emits_set_flags(tri_mesh):
    obj = build_wall_scenery(
        _wall_config(is_allowed_on_slope=True, has_glass=True),
        [tri_mesh],
    )
    props = build_wall_scenery_json(obj)["properties"]
    assert props["isAllowedOnSlope"] is True
    assert props["hasGlass"] is True


def test_door_json_emits_isdoor_and_drops_glass(tri_mesh):
    obj = build_wall_scenery(
        _wall_config(is_door=True, has_glass=True, animation=_door_frames()),
        [tri_mesh],
    )
    props = build_wall_scenery_json(obj)["properties"]
    assert props["isDoor"] is True
    assert "hasGlass" not in props  # a door takes its own paint path, no glass block


def test_door_json_drops_allowed_on_slope(tri_mesh, caplog):
    obj = build_wall_scenery(
        _wall_config(is_door=True, is_allowed_on_slope=True, animation=_door_frames()),
        [tri_mesh],
    )
    with caplog.at_level("WARNING"):
        props = build_wall_scenery_json(obj)["properties"]
    # The 36-image door table has no slope sprites, so the flag is dropped.
    assert "isAllowedOnSlope" not in props
    assert "isAllowedOnSlope" in caplog.text


def test_wall_json_emits_door_sound_and_scrolling(tri_mesh):
    obj = build_wall_scenery(
        _wall_config(door_sound=2, scrolling_mode=2, is_door=True, animation=_door_frames()),
        [tri_mesh],
    )
    props = build_wall_scenery_json(obj)["properties"]
    assert props["doorSound"] == 2
    assert props["scrollingMode"] == 2


@pytest.mark.parametrize("bad", [-1, 3, 7])
def test_wall_door_sound_out_of_range_rejected(tri_mesh, bad):
    # The engine packs doorSound into 2 bits and indexes a 3-entry sound
    # table (none/door/portcullis), so anything outside 0-2 is invalid.
    with pytest.raises(LoadError, match="door_sound"):
        build_wall_scenery(
            _wall_config(door_sound=bad, is_door=True, animation=_door_frames()),
            [tri_mesh],
        )


def test_large_json_negates_and_scales_tile_coords(tri_mesh):
    from openrct2_scenery_generator.exporter import build_large_scenery_json

    obj = build_large_scenery(_large_config([{"x": 2, "y": 3, "z": 8}]), [tri_mesh])
    tile = build_large_scenery_json(obj)["properties"]["tiles"][0]
    assert tile["x"] == -2 * COORDS_PER_TILE
    assert tile["y"] == -3 * COORDS_PER_TILE
    assert tile["z"] == 8


def test_load_header_stores_version_when_set(tri_mesh):
    config = _wall_config(version="3.1")
    obj = build_wall_scenery(config, [tri_mesh])
    assert obj.version == "3.1"


def test_load_model_raises_when_absent(tri_mesh):
    with pytest.raises(LoadError, match='"model" not found'):
        build_small_scenery({"id": "t", "name": "T"}, [tri_mesh])


def test_load_model_raises_when_element_not_dict(tri_mesh):
    config = {"id": "t", "name": "T", "model": ["not_a_dict"]}
    with pytest.raises(LoadError, match='"model" is not an object'):
        build_small_scenery(config, [tri_mesh])


def test_load_model_raises_for_invalid_mesh_index(tri_mesh):
    config = {"id": "t", "name": "T", "model": [{"mesh_index": "bad"}]}
    with pytest.raises(LoadError, match='"mesh_index" not found or is not an integer'):
        build_small_scenery(config, [tri_mesh])


def test_load_model_raises_for_out_of_bounds_mesh_index(tri_mesh):
    config = {"id": "t", "name": "T", "model": [{"mesh_index": 99}]}
    with pytest.raises(LoadError, match="out of bounds"):
        build_small_scenery(config, [tri_mesh])


def test_animation_frames_not_list_raises(tri_mesh):
    config = {
        "id": "t", "name": "T",
        "animation": {"frame_offsets": [0], "frames": "not_a_list"},
    }
    with pytest.raises(LoadError, match='"animation.frames"'):
        build_small_scenery(config, [tri_mesh])


def test_animation_frames_empty_raises(tri_mesh):
    config = {
        "id": "t", "name": "T",
        "animation": {"frame_offsets": [0], "frames": []},
    }
    with pytest.raises(LoadError, match='"animation.frames"'):
        build_small_scenery(config, [tri_mesh])


def test_animation_frames_mismatched_entry_count_raises(tri_mesh):
    config = {
        "id": "t", "name": "T",
        "animation": {
            "frame_offsets": [0, 1],
            "frames": [
                [{"mesh_index": 0}],
                [{"mesh_index": 0}, {"mesh_index": -1}],
            ],
        },
    }
    with pytest.raises(LoadError, match="same number of model entries"):
        build_small_scenery(config, [tri_mesh])


def test_animation_not_dict_raises(tri_mesh):
    config = {"id": "t", "name": "T", "animation": "not_a_dict"}
    with pytest.raises(LoadError, match='"animation" is not an object'):
        build_small_scenery(config, [tri_mesh])


def test_animation_frame_offsets_missing_raises(tri_mesh):
    config = {
        "id": "t", "name": "T",
        "animation": {"frames": [[{"mesh_index": 0}]]},
    }
    with pytest.raises(LoadError, match='"animation.frame_offsets"'):
        build_small_scenery(config, [tri_mesh])


def test_animation_frame_offsets_empty_raises(tri_mesh):
    config = {
        "id": "t", "name": "T",
        "animation": {"frame_offsets": [], "frames": [[{"mesh_index": 0}]]},
    }
    with pytest.raises(LoadError, match='"animation.frame_offsets"'):
        build_small_scenery(config, [tri_mesh])


def test_tiles_element_not_dict_raises(tri_mesh):
    with pytest.raises(LoadError, match="must be an object"):
        build_large_scenery(_large_config(["not_a_dict"]), [tri_mesh])


def _write_tri_obj(tmp_path):
    p = tmp_path / "m.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    return p


def test_load_small_scenery_from_file(tmp_path, monkeypatch):
    _write_tri_obj(tmp_path)
    cfg = {
        "id": "rct2.t", "name": "T",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    (tmp_path / "small.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    obj = load_small_scenery(tmp_path / "small.json")
    assert obj.id == "rct2.t"


def test_load_small_scenery_resolves_meshes_against_config_dir(tmp_path, monkeypatch):
    # Config + mesh live together; the loader must find them no matter the CWD.
    config_dir = tmp_path / "assets"
    config_dir.mkdir()
    _write_tri_obj(config_dir)
    cfg = {
        "id": "rct2.t", "name": "T",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    (config_dir / "small.json").write_text(json.dumps(cfg))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    obj = load_small_scenery(config_dir / "small.json")
    assert len(obj.meshes) == 1


def test_load_small_scenery_falls_back_to_cwd_meshes(tmp_path, monkeypatch):
    # An older config with CWD-relative mesh paths still loads from the CWD.
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    cfg = {
        "id": "rct2.t", "name": "T",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    (config_dir / "small.json").write_text(json.dumps(cfg))
    _write_tri_obj(tmp_path)
    monkeypatch.chdir(tmp_path)
    obj = load_small_scenery(config_dir / "small.json")
    assert len(obj.meshes) == 1


def test_load_large_scenery_from_file(tmp_path, monkeypatch):
    _write_tri_obj(tmp_path)
    cfg = {
        "id": "rct2.lg", "name": "Large",
        "object_type": "scenery_large",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": [{"x": 0, "y": 0}],
    }
    (tmp_path / "large.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    obj = load_large_scenery(tmp_path / "large.json")
    assert obj.id == "rct2.lg"


def test_load_wall_scenery_from_file(tmp_path, monkeypatch):
    _write_tri_obj(tmp_path)
    cfg = {
        "id": "rct2.wl", "name": "Wall",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    (tmp_path / "wall.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    obj = load_wall_scenery(tmp_path / "wall.json")
    assert obj.id == "rct2.wl"


def _banner_config(**overrides):
    base = {
        "id": "openrct2sg.footpath_banner.t",
        "name": "B",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    base.update(overrides)
    return base


def test_banner_loads_fields(tri_mesh):
    obj = build_banner(
        _banner_config(price=250, has_primary_colour=True, scrolling_mode=17), [tri_mesh]
    )
    assert obj.price == 250
    assert obj.has_primary_colour is True
    assert obj.scrolling_mode == 17
    assert obj.num_sprites == 8


def test_load_banner_from_file(tmp_path, monkeypatch):
    _write_tri_obj(tmp_path)
    cfg = {
        "id": "rct2.bn", "name": "Banner",
        "object_type": "footpath_banner",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    (tmp_path / "banner.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    from openrct2_scenery_generator.loader import load_banner

    obj = load_banner(tmp_path / "banner.json")
    assert obj.id == "rct2.bn"


def _item_config(**overrides):
    base = {
        "id": "openrct2sg.footpath_item.t",
        "name": "I",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    base.update(overrides)
    return base


def test_path_addition_rejects_unknown_render_as(tri_mesh):
    with pytest.raises(LoadError, match="Unrecognized render_as"):
        build_path_addition(_item_config(render_as="spaceship"), [tri_mesh])


def test_path_addition_defaults_allowed_flags(tri_mesh):
    obj = build_path_addition(_item_config(render_as="lamp"), [tri_mesh])
    assert obj.is_allowed_on_queue is True
    assert obj.is_allowed_on_slope is True


@pytest.mark.parametrize(
    ("render_as", "breakable", "expected"),
    [
        ("lamp", False, 5),
        ("lamp", True, 9),
        ("bench", True, 9),
        ("bin", False, 13),
        ("fountain", False, 5),
    ],
)
def test_path_addition_sprite_count(tri_mesh, render_as, breakable, expected):
    obj = build_path_addition(
        _item_config(render_as=render_as, is_breakable=breakable), [tri_mesh]
    )
    assert obj.num_sprites == expected


def test_path_addition_loads_optional_broken_full_meshes(tmp_path, monkeypatch):
    _write_tri_obj(tmp_path)
    cfg = _item_config(
        render_as="bin",
        meshes=["m.obj"],
        broken_meshes=["m.obj"],
        broken_model=[{"mesh_index": 0, "position": [0, 0, 0]}],
        full_meshes=["m.obj"],
        full_model=[{"mesh_index": 0, "position": [0, 0, 0]}],
    )
    monkeypatch.chdir(tmp_path)
    from openrct2_scenery_generator.loader import load_path_addition

    (tmp_path / "item.json").write_text(json.dumps(cfg))
    obj = load_path_addition(tmp_path / "item.json")
    assert len(obj.broken_meshes) == 1
    assert len(obj.full_meshes) == 1


def test_path_addition_broken_full_meshes_resolve_against_config_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "assets"
    config_dir.mkdir()
    _write_tri_obj(config_dir)
    cfg = _item_config(
        render_as="bin",
        meshes=["m.obj"],
        broken_meshes=["m.obj"],
        broken_model=[{"mesh_index": 0, "position": [0, 0, 0]}],
        full_meshes=["m.obj"],
        full_model=[{"mesh_index": 0, "position": [0, 0, 0]}],
    )
    (config_dir / "item.json").write_text(json.dumps(cfg))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    from openrct2_scenery_generator.loader import load_path_addition

    obj = load_path_addition(config_dir / "item.json")
    assert len(obj.broken_meshes) == 1
    assert len(obj.full_meshes) == 1


def test_scenery_group_loads_entries_without_meshes():
    obj = build_scenery_group(
        {
            "id": "openrct2sg.scenery_group.t",
            "name": "G",
            "priority": 12,
            "entries": ["a.b.c", "d.e.f"],
        }
    )
    assert obj.priority == 12
    assert obj.entries == ["a.b.c", "d.e.f"]


def test_load_scenery_group_from_file(tmp_path, monkeypatch):
    cfg = {
        "id": "openrct2sg.scenery_group.t",
        "name": "G",
        "object_type": "scenery_group",
        "entries": ["a.b.c"],
    }
    (tmp_path / "group.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    obj = load_scenery_group(tmp_path / "group.json")
    assert obj.entries == ["a.b.c"]


def test_load_scenery_group_preview_resolves_against_config_dir(tmp_path, monkeypatch):
    from openrct2_x7_renderer.image import write_png
    from openrct2_x7_renderer.types import IndexedImage

    config_dir = tmp_path / "assets"
    config_dir.mkdir()
    write_png(IndexedImage.blank(4, 4), config_dir / "icon.png")
    cfg = {
        "id": "openrct2sg.scenery_group.t",
        "name": "G",
        "object_type": "scenery_group",
        "preview": "icon.png",
    }
    (config_dir / "group.json").write_text(json.dumps(cfg))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    obj = load_scenery_group(config_dir / "group.json")
    assert obj.preview is not None
    assert obj.preview.width == 4
