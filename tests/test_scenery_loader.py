"""Tests for shared scenery config validation, object-type dispatch, the
tile-centre mapping, and the wall/large object.json flag emission rules."""

import numpy as np
import pytest
from openrct2_scenery_generator.constants import COORDS_PER_TILE
from openrct2_scenery_generator.exporter import (
    _tile_centers_xz,
    build_wall_scenery_json,
)
from openrct2_scenery_generator.loader import (
    LoadError,
    build_large_scenery,
    build_wall_scenery,
    object_type_of,
)
from openrct2_x7_renderer.constants import TILE_SIZE
from openrct2_x7_renderer.mesh import load_mesh


@pytest.fixture
def tri_mesh(tmp_path):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    return load_mesh(tmp_path / "m.obj")


# --- object_type_of ---------------------------------------------------------


def test_object_type_defaults_to_small():
    assert object_type_of({}) == "scenery_small"


@pytest.mark.parametrize("t", ["scenery_small", "scenery_large", "scenery_wall"])
def test_object_type_accepts_known_types(t):
    assert object_type_of({"object_type": t}) == t


def test_object_type_rejects_unknown():
    with pytest.raises(LoadError, match="Unrecognized object_type"):
        object_type_of({"object_type": "scenery_huge"})


# --- units_per_tile validation ----------------------------------------------


def _wall_config(**overrides):
    base = {
        "id": "openrct2sg.scenery_wall.t",
        "name": "T",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("bad", [0, -4.0])
def test_units_per_tile_must_be_positive(tri_mesh, bad):
    with pytest.raises(LoadError, match="units_per_tile"):
        build_wall_scenery(_wall_config(units_per_tile=bad), [tri_mesh])


def test_units_per_tile_defaults_to_tile_size(tri_mesh):
    obj = build_wall_scenery(_wall_config(), [tri_mesh])
    assert obj.units_per_tile == TILE_SIZE


# --- large scenery tile loading + centre mapping ----------------------------


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
    # Tile (x,y) index -> OBJ (X, Z) at units_per_tile per tile. NOT negated
    # (the sign flip lives only in the object.json tile coords).
    assert np.allclose(centers, [[0.0, 0.0], [TILE_SIZE, 2 * TILE_SIZE]])


def test_tile_centers_honour_render_scale(tri_mesh):
    obj = build_large_scenery(
        _large_config([{"x": 1, "y": 0}], units_per_tile=10.0), [tri_mesh]
    )
    assert np.allclose(_tile_centers_xz(obj), [[10.0, 0.0]])


def test_tile_centers_empty_when_no_tiles():
    # _tile_centers_xz must tolerate an empty tile list (degenerate shape).
    from openrct2_scenery_generator.types import LargeScenery

    assert _tile_centers_xz(LargeScenery()).shape == (0, 2)


# --- wall object.json flag emission -----------------------------------------


def test_wall_json_omits_unset_flags(tri_mesh):
    props = build_wall_scenery_json(build_wall_scenery(_wall_config(), [tri_mesh]))["properties"]
    # Only price/cursor/height are unconditional; the boolean capability flags
    # are emitted only when true (absent => false in the engine).
    for key in ("hasGlass", "isDoubleSided", "isAllowedOnSlope", "isDoor", "isOpaque"):
        assert key not in props
    # scrollingMode is omitted unless it's an actual scrolling sign (default 255
    # means "none"; emitting 0 paints garbage text).
    assert "scrollingMode" not in props


def test_wall_json_emits_set_flags(tri_mesh):
    obj = build_wall_scenery(
        _wall_config(is_allowed_on_slope=True, has_glass=True, is_door=True),
        [tri_mesh],
    )
    props = build_wall_scenery_json(obj)["properties"]
    assert props["isAllowedOnSlope"] is True
    assert props["hasGlass"] is True
    assert props["isDoor"] is True


def test_wall_json_emits_door_sound_and_scrolling(tri_mesh):
    obj = build_wall_scenery(
        _wall_config(door_sound=3, scrolling_mode=2, is_door=True), [tri_mesh]
    )
    props = build_wall_scenery_json(obj)["properties"]
    assert props["doorSound"] == 3
    assert props["scrollingMode"] == 2


def test_large_json_negates_and_scales_tile_coords(tri_mesh):
    from openrct2_scenery_generator.exporter import build_large_scenery_json

    obj = build_large_scenery(_large_config([{"x": 2, "y": 3, "z": 8}]), [tri_mesh])
    tile = build_large_scenery_json(obj)["properties"]["tiles"][0]
    assert tile["x"] == -2 * COORDS_PER_TILE
    assert tile["y"] == -3 * COORDS_PER_TILE
    # z/clearance are already coordinate units -> not negated.
    assert tile["z"] == 8
