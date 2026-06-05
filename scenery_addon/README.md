# scenery_addon

The Blender 4.2+ add-on (extension). It is the UI + scene adapter only: the
whole pipeline — config validation, rendering, `.parkobj` assembly — lives in the
bundled [`openrct2_scenery_generator`](../openrct2_scenery_generator/) and
[`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) wheels.
This package reads the Blender scene, hands the core an in-memory config dict +
`Mesh` list, and surfaces the result in the viewport.

It ships as a separate extension (`id = "openrct2sg"`) from the vehicle add-on
(`openrct2vg`), so both can be installed at once.

## How it works

1. **Properties** (`props.py`): native Blender `PropertyGroup`s store the entire
   object in the `.blend` file — object-wide settings on `scene.vgs_scenery`,
   per-object role on `object.vgs_object`, per-material region/shading on
   `material.vgs_material`. Enum item lists are sourced from the installed
   `openrct2_scenery_generator` package, so the UI can never offer a value the
   loader would reject.
2. **Panels** (`panels.py`): draw those properties in the 3D Viewport **OpenRCT2**
   sidebar tab — `VGS_PT_scenery` (object-wide) and `VGS_PT_object_view3d` (active
   object + its materials) — plus the `UIList`s for the large-scenery tile list
   (`VGS_UL_tiles`) and custom lights (`VGS_UL_lights`). The selected-object panel
   shares a `bl_idname` with the vehicle add-on's parent so the two extensions
   stack cleanly under one header.
3. **Scene adapter** (`scene_to_scenery.py`): the `bpy → Mesh` bridge. It bakes
   each geometry object's world transform into an in-memory `Mesh` (no OBJ files
   written), converts Blender axes to OBJ space, and builds the per-`object_type`
   config dict the core expects. For animated small scenery it samples every
   geometry object across N evenly-spaced frames (`_sample_animation_poses`) and
   synthesizes the engine's `frameOffsets` table.
4. **Operators** (`operators.py`): `vgs.test_render` renders a single viewpoint
   and loads it into an Image Editor for fast iteration; `vgs.export_parkobj`
   renders every sprite on a background thread (spinner in the status bar) and
   writes the `.parkobj`. `vgs.tile_add`/`vgs.tile_remove` and
   `vgs.light_add`/`vgs.light_remove` manage the tile and light `UIList`s. All
   call the same core `build_*_scenery` → render → export path the CLI uses.

`__init__.py` registers props → operators → panels in that order (panels draw
properties, so the property groups must exist first).

## Coordinate convention

OBJ space is +X forward, +Y up, +Z right. A Blender vertex `(bx, by, bz)` maps to
OBJ `(bx, bz, -by)` via the `_BASIS` matrix — a proper rotation (det = +1), so
triangle winding is preserved. 1 tile = `TILE_SIZE` OBJ units. The animation
sampler emits rigid per-pose deltas with `to_euler("YZX")` to match the
renderer's `rotate_y(a) @ rotate_z(b) @ rotate_x(c)` ordering; see the module
docstring in `scene_to_scenery.py`.

## Material classification

Materials carry their role in `material.vgs_material` (region/remap, masks, AO and
edge flags, glass, wall side). The wall splitters read `is_glass` and the
`FRONT`/`BACK` side to peel the glass overlay and the double-sided rear block,
mirroring the MTL `*Glass*` / `*Front*` / `*Back*` name rules used by the CLI
path.

## Packaging model

Blender extensions run in an isolated Python environment and install **only** the
wheels listed in `blender_manifest.toml`; pip is never consulted at install time.
So everything the add-on imports must be vendored as a wheel for every
platform × Python combination Blender ships. Three kinds of wheel are bundled
under `wheels/`:

| Wheel | Source | Variants |
|---|---|---|
| `openrct2_x7_renderer` | PyPI (Embree-vendored native extension) | per platform × CPython 3.11/3.13 |
| `numpy`, `pillow`, `pyyaml` | PyPI | per platform × CPython 3.11/3.13 |
| `openrct2_scenerygenerator` | this repo (`uv build --wheel`, pure Python) | one `py3-none-any` for all targets |

## Building the extension

```bash
# Local single-platform build for the Blender on THIS machine:
uv run python scripts/build_plugin_local.py

# Refresh the committed wheels/ + manifest for all target platforms:
uv build --wheel                              # build the front-end wheel first
uv run python scripts/collect_wheels.py       # download deps, regenerate manifest
blender --command extension build             # zip the extension
```

`build_plugin_local.py` stages everything in a temp dir and never touches the
committed `wheels/` or `blender_manifest.toml`. Multi-platform release zips are
produced by CI ([`.github/workflows/build-plugin.yml`](../.github/workflows/build-plugin.yml)),
triggered manually or on a `v*` tag.

## Source layout

```
scenery_addon/
├── __init__.py            # register/unregister (props -> operators -> panels)
├── blender_manifest.toml  # extension manifest (id, version, platforms, wheels)
├── props.py               # PropertyGroups: scene/object/material data + tile/light lists
├── panels.py              # 3D Viewport OpenRCT2 sidebar panels + UILists
├── operators.py           # vgs.test_render + threaded vgs.export_parkobj + tile/light ops
├── scene_to_scenery.py    # bpy -> Mesh adapter + per-object_type config-dict builder
└── wheels/                # vendored wheels (regenerated by collect_wheels.py)
```

## License

GPL-3.0-or-later. The bundled wheels carry Embree + TBB (Apache-2.0); their
license texts ship alongside in the extension zip.
