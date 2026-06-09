# OpenRCT2 Scenery Generator

A modern Blender add-on to author and export OpenRCT2 scenery objects (small scenery, large multi-tile scenery, and 
walls) from 3D meshes. Geometry is ray-traced into the isometric sprite sheets OpenRCT2 expects and packaged as a 
ready-to-install `.parkobj`.

Rendering is handled by the external [`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) package
(an Embree-backed ray tracer shipping prebuilt, vendored wheels).

## Requirements

- Windows x64, macOS arm64, Linux x64
- Blender 4.2 or newer
  - Tested on Blender 5.1.2

## Setup

1. Download the latest version of the Blender add-on [here](https://github.com/alex-parisi/OpenRCT2-SceneryGenerator/releases/latest)
2. Install the add-on into Blender. If you are not sure how, follow [these instructions](doc/blender-plugin-installation.md)
3. Follow the tutorial [here]()

## Documentation

For a more exhaustive list of the available UI settings and how to use them, review the [reference material](doc/reference.md)

## CLI Usage

```
openrct2-scenery-generator [--test|--skip-render] <input.json|.yaml>
```

- `--test`: render a single viewpoint per object to `test/` for fast iteration
  (no `.parkobj` produced).
- `--skip-render`: emit `object.json` / packaging without re-rendering sprites.

The config format is JSON or YAML (chosen by file extension). The top-level
`object_type` field selects the path:

| `object_type`     | Output                  |
|-------------------|-------------------------|
| `scenery_small`   | single-tile scenery (default if omitted) |
| `scenery_large`   | multi-tile scenery      |
| `scenery_wall`    | tile-edge wall          |
| `footpath_banner` | path-edge banner / sign |
| `footpath_item`   | path addition (lamp, bin, bench, fountain, TV) |
| `scenery_group`   | a scenery tab (name + icon + member ids); no geometry |

### CLI Quickstart

```bash
uv sync

# Quick single-viewpoint render of an example, written to test/. Fast iteration.
uv run openrct2-scenery-generator --test examples/scenery_small/obelisk.yaml

# Full render: writes object/ and <id>.parkobj in the output directory.
uv run openrct2-scenery-generator examples/scenery_large/gate.yaml
```

Install the resulting `.parkobj` into OpenRCT2's `object/` directory and
**restart** the game (it doesn't hot-reload objects).

## Mesh convention

OBJ meshes use **+X = forward**, **+Y = up**, **+Z = right**, with one tile =
`TILE_SIZE` units. Materials are classified by **name** (`Remap1` for primary
colour remap, `*Glass*` for translucent wall panels, `*Front*` / `*Back*` for
double-sided wall faces, etc.). The per-object-type anchoring rules are
documented inline in `openrct2_scenery_generator/sprite_renderer.py`.

## License

GPL-3.0-or-later
