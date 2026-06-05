# OpenRCT2 Scenery Generator

Author and export **OpenRCT2 scenery objects** — small scenery, large
(multi-tile) scenery, and walls — from 3D meshes. Geometry is ray-traced into
the isometric sprite sheets OpenRCT2 expects and packaged as a ready-to-install
`.parkobj`.

Rendering is handled by the external
[`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) package
(an Embree-backed ray tracer shipping prebuilt, vendored wheels), so this repo is
pure Python — no compiler or Embree needed.

> This is the scenery sibling of **OpenRCT2-VehicleGenerator**; both share the
> same renderer and packaging approach.

## Documentation

| Guide | For |
|---|---|
| [Quickstart](#quickstart) / [CLI usage](#cli-usage) | Rendering an example from the command line |
| [`openrct2_scenery_generator/`](openrct2_scenery_generator/README.md) | The Python core (config → render → `.parkobj`) |
| [`scenery_addon/`](scenery_addon/README.md) | The Blender add-on internals (for contributors) |
| [Example configs](#example-configs) | The YAML/JSON config used by the CLI |

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) — `uv sync` pulls everything,
  including the renderer wheel from PyPI.

## Quickstart

```bash
uv sync

# Quick single-viewpoint render of an example, written to test/. Fast iteration.
uv run openrct2-scenery-generator --test examples/scenery_small/obelisk.yaml

# Full render: writes object/ and <id>.parkobj in the output directory.
uv run openrct2-scenery-generator examples/scenery_large/gate.yaml
```

Install the resulting `.parkobj` into OpenRCT2's `object/` directory and
**restart** the game (it doesn't hot-reload objects).

## CLI Usage

```
openrct2-scenery-generator [--test|--skip-render] <input.json|.yaml>
```

- `--test` — render a single viewpoint per object to `test/` for fast iteration
  (no `.parkobj` produced).
- `--skip-render` — emit `object.json` / packaging without re-rendering sprites.

The config format is JSON or YAML (chosen by file extension). The top-level
`object_type` field selects the path:

| `object_type`    | Output                  |
|------------------|-------------------------|
| `scenery_small`  | single-tile scenery (default if omitted) |
| `scenery_large`  | multi-tile scenery      |
| `scenery_wall`   | tile-edge wall          |

### Example configs

**Small scenery** (`examples/scenery_small/obelisk.yaml`):

```yaml
id: author.scenery_small.obelisk
name: Stone Obelisk
authors: [you]
version: "1.0"
output_directory: .
meshes:
  - examples/scenery_small/obelisk.obj
model:
  - {mesh_index: 0, position: [0, 0, 0], orientation: [0, 0, 0]}
price: 2.0
removal_price: 1.5
cursor: CURSOR_STATUE_DOWN
height: 64
shape: "4/4"
is_rotatable: true
has_primary_colour: true
```

**Large scenery** adds a `tiles:` footprint (friendly tile **indices**, not
coordinate units):

```yaml
object_type: scenery_large
# ...
tiles:
  - {x: 0, y: 0, z: 0, clearance: 40}
  - {x: 1, y: 0, z: 0, clearance: 40}
```

**Walls** use `object_type: scenery_wall`; flag `is_allowed_on_slope`,
`has_glass`, or `is_double_sided` to select the sprite-block layout. See
`examples/scenery_wall/` for flat, glass, and double-sided walls.

## Mesh convention

OBJ meshes use **+X = forward**, **+Y = up**, **+Z = right**, with one tile =
`TILE_SIZE` units. Materials are classified by **name** (`Remap1` for primary
colour remap, `*Glass*` for translucent wall panels, `*Front*` / `*Back*` for
double-sided wall faces, etc.). The per-object-type anchoring rules are
documented inline in `openrct2_scenery_generator/sprite_renderer.py`.

## Blender add-on

`scenery_addon/` is a Blender extension that authors and exports scenery
directly from a Blender scene. Build a local install zip with:

```bash
uv run python scripts/build_plugin_local.py --install
```

(macOS; for Linux/Windows release builds use the `build-plugin` CI workflow.)
The add-on bundles the renderer + this repo's front-end as wheels, so it runs
inside Blender's isolated Python with no extra install steps.

## Development

```bash
uv sync
uv run pytest                 # tests
uv run mypy                   # type check
uv run ruff check .           # lint
uv run yamllint examples      # lint scenery configs
```

See [`openrct2_scenery_generator/`](openrct2_scenery_generator/README.md) for the
architecture. The hard-won OpenRCT2 format gotchas (the `images.dat` sprite
layout, the large-scenery anchor, and the wall sub-pixel rules) are documented
inline in `sprite_renderer.py` and `exporter.py`.
