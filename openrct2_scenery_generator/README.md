# openrct2_scenery_generator

The pure-Python front-end that turns a scenery config (YAML/JSON or an in-memory
dict) into a finished OpenRCT2 `.parkobj`. It owns everything *scenery*-specific
— the three object schemas (`scenery_small`, `scenery_large`, `scenery_wall`),
the per-view render dispatch, and `.parkobj` assembly — and calls into
[`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) for the
actual ray tracing, OBJ/MTL parsing, RCT2 palette, and `images.dat` packing.

This is the scenery sibling of
[`openrct2_vehicle_generator`](https://github.com/alex-parisi/OpenRCT2-VehicleGenerator);
both share the same renderer and packaging approach.

## How it works

A render goes through three stages, each in its own module:

1. **Load** (`loader.py`): `object_type_of(config)` picks the object kind, then
   `build_small_scenery` / `build_large_scenery` / `build_wall_scenery` validate
   a parsed config dict and return the matching dataclass (`types.py`). Each
   resolves config strings to flags/shapes via `constants.py`, validates the
   footprint shape and tile list, and (for animated small scenery) transposes the
   per-pose `model` lists into per-mesh frame lists. `load_small_scenery(path)`
   (and the `_large` / `_wall` variants) are the convenience wrappers that parse
   the file and load meshes + preview from disk first.
2. **Render** (`sprite_renderer.py`): scenery needs only the cardinal rotations
   (`VIEWS[i] == rotate_y(i·π/2)`), so each view renders the prepared scene under
   the first `num_rotations` views. The same count tables (`count_small_scenery_sprites`,
   `count_large_scenery_sprites`, `WallScenery.num_sprites`) feed both the
   declared `images` count and the rendered set, so they can never drift. The
   large-scenery and wall paths re-anchor the model per view (per-direction tile
   corner; per-diagonal sub-pixel nudge) and bin faces to tiles, so they render
   each sprite in its own scene.
3. **Export** (`exporter.py`): `build_*_scenery_json` emits the OpenRCT2
   `object.json` (properties + per-tile data + flags). `export_*_scenery` renders
   every sprite, concatenates them into one `images.dat`, references it via the
   `$LGX:` syntax, and zips the pair into `<id>.parkobj`.

`__main__.py` wires these together behind the `openrct2-scenery-generator` CLI,
reusing X7's `run_cli`/`make_context` helpers so the CLI flags, config parsing,
and default light rig match the renderer's. A small `_DISPATCH` table maps each
`object_type` to its `(load, export, export_test)` triple.

## Coordinate convention

Mesh OBJs use **+X = forward**, **+Y = up**, **+Z = right**; 1 tile =
`TILE_SIZE` units. Orientation Euler angles `[a, b, c]` (degrees) are applied as
`rotate_y(a) @ rotate_z(b) @ rotate_x(c)` — so `[0, 90, 0]` rotates around the
**Z** axis, not Y.

## Public API

```python
from openrct2_scenery_generator.loader import load_small_scenery, build_small_scenery
from openrct2_scenery_generator.exporter import export_small_scenery, build_small_scenery_json
from openrct2_x7_renderer.cli import make_context

obj = load_small_scenery("examples/scenery_small/obelisk.yaml")   # parse + load meshes
context = make_context(lights=[], units_per_tile=obj.units_per_tile, test=False)
export_small_scenery(obj, context, output_directory=".")          # writes <id>.parkobj
```

| Function | Module | Purpose |
|---|---|---|
| `object_type_of(config)` | `loader` | The config's object kind (`scenery_small` default). |
| `load_{small,large,wall}_scenery(path)` | `loader` | Parse a config file, load its meshes + preview, build the dataclass. |
| `build_{small,large,wall}_scenery(config, meshes, preview=None)` | `loader` | Build from an already-parsed dict + in-memory meshes (used by the Blender add-on, which has no files to read). |
| `build_{small,large,wall}_scenery_json(obj)` | `exporter` | Produce the `object.json` dict (no rendering). |
| `export_{small,large,wall}_scenery(obj, ctx, out_dir)` | `exporter` | Render all sprites and write `<id>.parkobj` into `out_dir`. |
| `export_{small,large,wall}_scenery_to(obj, ctx, parkobj_path, work_dir)` | `exporter` | Same, with caller-chosen paths; `skip_render=True` reuses a prior `images.dat`. |
| `export_{small,large,wall}_scenery_test(obj, ctx)` | `exporter` | One viewpoint per sprite to `test/` for fast iteration. |

## Object kinds

| `object_type` | Sprites | Notes |
|---|---|---|
| `scenery_small` | 1 (fixed) or 4 (rotatable); `(max(frameOffsets)+1)·4` when animated | Origin = tile centre; matches the engine's `{15,15}` paint offset. Animates via the generic `frameOffsets` path. |
| `scenery_large` | `4 + 4·numTiles` (4 reserved preview + tile-major, rotation-minor) | Per-direction corner anchor; tile coords are coordinate units (32/tile), sign-negated. Does **not** animate. |
| `scenery_wall` | 2 (flat), 6 (+slope), or 12 (glass / double-sided) | Panel along a tile-edge diagonal; glass and front/back are split by material name. |

See the [root README](../README.md) for the full config schema. The hard-won
OpenRCT2 format gotchas (the `scrollingMode` 255 default, the per-direction
large-scenery corner, the wall sub-pixel anchors) are documented inline in
`sprite_renderer.py` and `exporter.py`.

## CLI

```bash
# Fast single-viewpoint render per sprite, written to test/.
uv run openrct2-scenery-generator --test examples/scenery_small/obelisk.yaml

# Full render: writes object/ and <id>.parkobj in the output directory.
uv run openrct2-scenery-generator examples/scenery_large/gate.yaml

# Reuse the previous run's images.dat (rebuild object.json only).
uv run openrct2-scenery-generator --skip-render examples/scenery_wall/glass_wall.yaml
```

All paths in the config (`meshes`, `preview`, and `map_Kd` lines in `.mtl`
files) resolve relative to the **current working directory**.

## Source layout

```
openrct2_scenery_generator/
├── __init__.py          # package version (from importlib.metadata)
├── __main__.py          # `openrct2-scenery-generator` CLI entry point + dispatch table
├── constants.py         # shapes, default cursor/height, COORDS_PER_TILE, scrolling sentinel
├── types.py             # SmallScenery / LargeScenery / WallScenery dataclasses + tiles
├── loader.py            # config dict -> Scenery (validation, animated-model transpose)
├── sprite_renderer.py   # per-view render dispatch (small / large / wall) + sprite-count tables
└── exporter.py          # object.json builder + images.dat packing + .parkobj zip
```

## Development

```bash
uv sync                      # install the package + dev tools
uv run pytest                # tests (coverage on by default via pyproject.toml)
uv run ruff check .          # lint
uv run mypy                  # type-check
uv run yamllint examples     # lint the hand-authored example configs
```

The package is pure Python; the Embree-backed renderer installs from PyPI as a
prebuilt wheel, so no compiler or CMake is needed.

## License

GPL-3.0-or-later. Depends on `openrct2-x7-renderer` (also GPL-3.0-or-later;
its distributed wheels bundle Embree and TBB, Apache-2.0).
