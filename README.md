# OpenRCT2 Scenery Generator

Author and export OpenRCT2 scenery objects (small scenery, large multi-tile
scenery, and walls) from 3D meshes. Geometry is ray-traced into the isometric
sprite sheets OpenRCT2 expects and packaged as a ready-to-install `.parkobj`.

Rendering is handled by the external
[`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) package
(an Embree-backed ray tracer shipping prebuilt, vendored wheels), so this repo is
pure Python, with no compiler or Embree needed.

> This is the scenery sibling of **OpenRCT2-VehicleGenerator**; both share the
> same renderer and packaging approach.

## Documentation

| Guide | For |
|---|---|
| [Quickstart](#quickstart) / [CLI usage](#cli-usage) | Rendering an example from the command line |
| [Add-on UI reference](#add-on-ui-reference) | Every control in the Blender add-on, exhaustively |
| [`openrct2_scenery_generator/`](openrct2_scenery_generator/README.md) | The Python core (config → render → `.parkobj`) |
| [`scenery_renderer_addon/`](scenery_renderer_addon/README.md) | The Blender add-on internals (for contributors) |
| [Example configs](#example-configs) | The YAML/JSON config used by the CLI |

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (recommended); `uv sync` pulls everything,
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

- `--test`: render a single viewpoint per object to `test/` for fast iteration
  (no `.parkobj` produced).
- `--skip-render`: emit `object.json` / packaging without re-rendering sprites.

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

`scenery_renderer_addon/` is a Blender extension that authors and exports scenery
directly from a Blender scene. Build a local install zip with:

```bash
uv run python scripts/build_plugin_local.py --install
```

(macOS; for Linux/Windows release builds use the `build-plugin` CI workflow.)
The add-on bundles the renderer + this repo's front-end as wheels, so it runs
inside Blender's isolated Python with no extra install steps.

### Add-on UI reference

Every control lives in the 3D Viewport sidebar (press <kbd>N</kbd>) under the
**OpenRCT2** tab. There are two panels:

- **OpenRCT2 Scenery** — scene-level: what to build and how (one scenery
  object per scene).
- **Selected Object → Scenery** — per-object and per-material settings for the
  mesh you have selected. (Shared with the vehicle add-on, which contributes
  its own sub-panel under the same "Selected Object" header.)

Every field below maps 1:1 to a key in the CLI config (see [Example
configs](#example-configs)); the UI is just a front-end for the same build.

#### Panel: OpenRCT2 Scenery (scene-level)

**Top of panel — what you're building**

| Control | Values / default | What it does |
|---|---|---|
| **Type** | Small Scenery *(default)* / Large Scenery / Wall | Selects the object kind. Changes which type-specific box appears below and which exporter runs. |
| **Scale** | Realistic (3.3 m/tile) *(default)* / 1 unit = 1 tile / Custom | How many OBJ units span one OpenRCT2 tile. Drives sprite size and the tile-anchor maths. "Realistic" matches RCT2's real-world tile scale; "1 unit = 1 tile" lets you model in tile units. |
| **Units / Tile** | float, default `3.3`, min `0.01` | Only shown when **Scale = Custom**. The raw units-per-tile value; the presets just write this for you. |

**Identity box** — object metadata written into `object.json`.

| Control | Default | What it does |
|---|---|---|
| **Object ID** | `openrct2sg.scenery_small.my_object` | Unique object id (e.g. `author.scenery_small.obj`). Avoid clashing with vanilla ids. Also seeds the default `.parkobj` filename on export. |
| **Name** | `My Scenery` | In-game display name. |
| **Authors** | *(empty)* | Comma-separated author list. |
| **Version** | `1.0` | Object version string. |

**Placement box** — gameplay/placement behaviour common to all types.

| Control | Default | What it does |
|---|---|---|
| **Price** | `2.0` | Build cost. |
| **Removal Price** | `1.0` | Refund/cost to remove. |
| **Cursor** | Statue Down | Mouse cursor shown while placing. Closed dropdown of the `CURSOR_*` ids OpenRCT2 accepts. |
| **Scenery Group** | *(empty)* | Optional scenery-group object id this belongs to. |
| **Primary Colour** | off | Make the object recolourable with a primary colour; pairs with **Remap 1** materials. |
| **Secondary Colour** | off | Adds a second placement colour; pairs with **Remap 2** materials. |

**Small Scenery box** *(Type = Small Scenery)*

| Control | Values / default | What it does |
|---|---|---|
| **Shape** | `1/4`, `2/4`, `3/4`, `4/4` *(default)*, `1/4+D`, `4/4+D` | Footprint: how many tile quadrants the object occupies. `+D` is a full-tile diagonal variant. |
| **Height** | int, default `64`, min `0` | Clearance height in Z coordinate units (8 units per height step). Gameplay value, independent of the rendered sprite. |
| **Rotatable** | on | Object has 4 rotations (renders 4 viewpoints) instead of 1. |
| **Stackable** | off | Can be stacked / placed on top of other scenery. |
| **Requires Flat Surface** | off | Only placeable on flat ground. |
| **Prohibit Walls** | off | Blocks walls on the same tile. |
| **Tree** | off | Flags the object as a tree (affects some gameplay rules). |

**Animation box** *(Type = Small Scenery)* — samples Blender keyframes into
animation poses. All controls below the toggle appear only when **Animated** is on.

| Control | Values / default | What it does |
|---|---|---|
| **Animated** | off | Turn the object into an animated small-scenery object by sampling scene keyframes. |
| **Cycle** | 4 / 8 *(default)* / 16 / 32 / 64 / 128 / 256 frames | Number of animation steps before looping. Must be a power of two (the engine masks the tick counter). Higher = more sprites. |
| **Playback** | Loop *(default)* / Ping-Pong | Loop replays 0…N-1 then jumps to 0; Ping-Pong plays forward then back (smooth for swings/pendulums). |
| **Speed (delay)** | int, default `1`, range `0–15` | Tick bit-shift: higher = slower playback. |
| **Deformation** | Auto *(default)* / Bake all / Rigid only | How animated geometry is sampled. **Auto** bakes a fresh mesh per pose only for objects with an armature/deform modifier or animated shape keys and keeps the rest rigid; **Bake all** re-extracts every object's mesh each pose (one mesh per pose — use for deformation Auto misses); **Rigid only** animates transforms only (deformation frozen at rest). |
| **Start Frame / End Frame** | `1` / `24` | Scene frame range to sample. If End ≤ Start the scene's own frame range is used. |

**Wall box** *(Type = Wall)* — model the panel running along OBJ **+Z**.

| Control | Default | What it does |
|---|---|---|
| **Height** | int, default `2`, min `1` | Wall height in wall units; the engine renders it `× 8` coordinate units tall (distinct from small scenery's `Height` clearance). |
| **Allowed on Slope** | on | Placeable on sloped terrain; adds the 4 slope sprites. |
| **Has Glass** | off | Wall has translucent glass panes; materials marked **Glass** are split into a separate overlay block. |
| **Double-Sided** | off | Distinct front/back faces (materials marked Front/Back via **Wall Side**); the rear block renders offset by +6. |
| **Tertiary Colour** | off | Adds a third placement colour; pairs with **Remap 3** materials. |

> Glass + double-sided isn't supported together — the UI warns and the
> double-sided flag is dropped.

**Large Scenery box** *(Type = Large Scenery)*

| Control | Values / default | What it does |
|---|---|---|
| **Tertiary Colour** | off | Adds a third placement colour; pairs with **Remap 3** materials. |
| **Photogenic** | off | Marks the object as a good photo subject (peeps take photos of it). |
| **Scrolling Mode** | int, default `255`, range `0–255` | `255` = no scrolling text. Only set a real mode for scrolling signs (mode 0 is a *valid, active* mode, so leave it at 255 otherwise). |
| **Tiles** | list | The multi-tile footprint. Use **＋ / －** to add/remove tiles; each tile exposes **X**, **Y** (tile *indices* along OBJ +X / +Z), **Z** (height offset, coordinate units) and **Clearance** (vertical clearance, coordinate units, default `40`). At least one tile is required. |

**Custom Lighting box** (collapsible — click the header arrow)

By default the object uses the built-in nine-light rig. Toggle **Custom
Lighting** to override it with your own list.

| Control | Values / default | What it does |
|---|---|---|
| **Custom Lighting** | off | When on, replaces the default rig with the lights below. With the list empty, the default rig is still used. |
| **(list) ＋ / －** | — | Add / remove a light. Each row shows its type and strength. |
| **Type** | Diffuse *(default)* / Specular | Directional diffuse light vs. specular highlight light. |
| **Casts Shadow** | off | Whether this light casts shadows. |
| **Direction** | `(0, 1, 0)` | Direction in OBJ space (+X forward, +Y up, +Z right); normalized at render time. |
| **Strength** | float, default `0.5`, min `0` | Intensity multiplier. |

**Bottom of panel**

| Control | What it does |
|---|---|
| **Preview Image** | Path to a preview image embedded in the object. |
| **Test Render** | Renders one viewpoint quickly and loads the sprite into an open Image Editor. Fast iteration; no `.parkobj` written. |
| **Export .parkobj** | Renders every sprite and writes a ready-to-install `.parkobj` (opens a file picker; defaults the name from **Object ID**). Both buttons run the renderer off the main thread with a status-bar spinner. |

#### Panel: Selected Object → Scenery (per-object)

Shown for the selected mesh object.

| Control | Values / default | What it does |
|---|---|---|
| **Role** | Geometry *(default)* / Ignore | Whether this object is part of the scenery model. **Ignore** excludes it from the render entirely (and hides the material controls below). |

**Materials box** — settings for the object's active material slot. With more
than one slot, a slot list lets you pick which material to edit. These replace
the MTL material-*name* keyword rules used by the CLI path.

| Control | Values / default | What it does |
|---|---|---|
| **Glass** *(walls only)* | off | Translucent glass pane; split into the wall's glass overlay block. |
| **Wall Side** *(walls only)* | Both Sides *(default)* / Front Only / Back Only | Which side of a double-sided wall this face belongs to. "Both" faces are shared. |
| **Region** | None *(default)* / Remap 1 (primary) / Remap 2 (secondary) / Remap 3 (tertiary) / Greyscale / Peep / Chain | How OpenRCT2 treats this material's pixels. The Remap regions are recoloured at runtime by the matching placement colour. |
| **Mask** | off | Treat as a collision/visibility mask. |
| **Visible Mask** | off | Mask that is also rendered. |
| **No Ambient Occlusion** | off | Disable AO for this material. |
| **Edge AA** | off | Enable background anti-aliasing blending on edges. |
| **Dark Edge AA** | off | Dark-variant background AA blending. |
| **No Bleed** | off | Disable colour bleed from neighbouring pixels. |
| **Flat Shaded** | off | Use flat (per-face) shading instead of smooth normals. |
| **Texture** | *(none)* | Optional image. Must be saved to disk — its file is read at export time. |

**Shading** (sub-section of the Materials box) — Phong controls.

| Control | Values / default | What it does |
|---|---|---|
| **Override Color** + **Color** | off / `(0.8, 0.8, 0.8)` | When on, use the picked flat diffuse colour instead of the shader's Base Color. The colour field is disabled until the toggle is on. |
| **Specular Exponent** | float, default `50`, min `1`, soft-max `256` | Phong highlight tightness: higher = smaller, sharper highlight. |
| **Specular Intensity** | float, default `0.5`, min `0`, soft-max `1` | Brightness of the specular highlight. |
| **Tint Highlight** + **Specular Tint** | off / white | When on, tint the specular highlight with the picked colour (off = white). The tint field is disabled until the toggle is on. |

## Development

```bash
uv sync
uv run pytest                 # tests
uv run mypy                   # type check
uv run ruff check .           # lint
uv run yamllint examples      # lint scenery configs
```

See [`openrct2_scenery_generator/`](openrct2_scenery_generator/README.md) for the
architecture. The OpenRCT2 format details (the `images.dat` sprite layout, the
large-scenery anchor, and the wall sub-pixel rules) are documented inline in
`sprite_renderer.py` and `exporter.py`.
