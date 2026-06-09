## Add-on UI reference

Every control lives in the 3D Viewport sidebar (press <kbd>N</kbd>) under the
**OpenRCT2** tab. There are two panels:

- **OpenRCT2 Scenery**: scene-level: what to build and how
- **Selected Object → Scenery**: per-object and per-material settings for the
  mesh you have selected

Every field below maps 1:1 to a key in the CLI config (see [Example
configs](#example-configs)); the UI is just a front-end for the same build.

### Panel: OpenRCT2 Scenery (scene-level)

**Top of panel — what you're building**

| Control | Values / default | What it does |
|---|---|---|
| **Type** | Small Scenery *(default)* / Large Scenery / Wall / Banner / Path Addition / Scenery Group | Selects the object kind. Changes which type-specific box appears below and which exporter runs. Scenery Group has no geometry, so it hides the scale/placement/lighting sections. |
| **Scale** | Realistic (3.3 m/tile) *(default)* / 1 unit = 1 tile / Custom | How many OBJ units span one OpenRCT2 tile. Drives sprite size and the tile-anchor maths. "Realistic" matches RCT2's real-world tile scale; "1 unit = 1 tile" lets you model in tile units. |
| **Units / Tile** | float, default `3.3`, min `0.01` | Only shown when **Scale = Custom**. The raw units-per-tile value; the presets just write this for you. |

**Identity box** — object metadata written into `object.json`.

| Control | Default | What it does |
|---|---|---|
| **Object ID** | `openrct2sg.scenery_small.my_object` | Unique object id (e.g. `author.scenery_small.obj`). Avoid clashing with vanilla ids. Also seeds the default `.parkobj` filename on export. |
| **Name** | `My Scenery` | In-game display name. |
| **Authors** | *(empty)* | Comma-separated author list. |
| **Version** | `1.0` | Object version string. |

**Placement box** — gameplay/placement behaviour. The fields shown adapt to the
type: banners drop Removal Price / Cursor / Secondary Colour; path additions show
only Price / Cursor / Scenery Group; scenery groups hide the box entirely.

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
| **Opaque** | off | Wall fully occludes the tile behind it (no see-through gaps). |
| **Door** | off | Make the wall an animated door (peeps pass through). Keyframe the leaf swinging open over the **Start/End Frame** range; the renderer samples 5 poses and mirrors them for the backward swing (36-image door table). **Long Door Animation** and an optional **Door Sound** id are nested under it. Mutually exclusive with **Animated**. |
| **Animated** | off | Cycle a flat-only **8-frame** animation sampled from the scene keyframes over the **Start/End Frame** range. Greys out slope/glass/double-sided (they'd alias the frames) and is mutually exclusive with **Door**. |

> Glass + double-sided isn't supported together — the UI warns and the
> double-sided flag is dropped. Doors and animated walls keyframe their geometry
> like animated small scenery (set **Deformation** + **Start/End Frame**); model
> a door's swinging leaf as the moving part and its posts/lintel as static so the
> static frame lands in the door's separate top-occlusion layer.

**Large Scenery box** *(Type = Large Scenery)*

| Control | Values / default | What it does |
|---|---|---|
| **Tertiary Colour** | off | Adds a third placement colour; pairs with **Remap 3** materials. |
| **Photogenic** | off | Marks the object as a good photo subject (peeps take photos of it). |
| **Scrolling Mode** | int, default `255`, range `0–255` | `255` = no scrolling text. Only set a real mode for scrolling signs (mode 0 is a *valid, active* mode, so leave it at 255 otherwise). |
| **Tiles** | list | The multi-tile footprint. Use **＋ / －** to add/remove tiles; each tile exposes **X**, **Y** (tile *indices* along OBJ +X / +Z), **Z** (height offset, coordinate units) and **Clearance** (vertical clearance, coordinate units, default `40`). At least one tile is required. |
| **Supports** / **Supports Above** *(per tile)* | off | Whether the selected tile draws vertical supports to the ground, and whether another object's supports may rest on top of it. |
| **Occupied Quadrants** *(per tile)* | all on | Which of the tile's 4 quadrants this piece fills (the `corners` mask; drives selection / terrain clipping). |
| **Wall Edges** *(per tile)* | all off | Which of the tile's 4 edges allow a wall against this piece (the `walls` mask). |

**Banner box** *(Type = Banner)* — model the sign + poles along the tile edge.

| Control | Default | What it does |
|---|---|---|
| **Scrolling Mode** | int, default `255`, range `0–255` | `255` = no scrolling text; set a real mode for a scrolling sign. |

Tag the sign material **Back** (rear pole) or **Front** (front pole + sign) via
the per-material **Banner Layer** picker; untagged faces fall into the front
layer. **Primary Colour** recolours a **Remap 1** sign.

**Path Addition box** *(Type = Path Addition)* — model the item centred on the
tile origin; the engine places it on open path edges.

| Control | Values / default | What it does |
|---|---|---|
| **Render As** | Lamp *(default)* / Bin / Bench / Fountain | How the engine draws & indexes the sprites. Also sets the matching draw-type flag (`isBin`/`isBench`/`isLamp`). |
| **Breakable** *(lamp/bench)* | off | Can be vandalised; adds a block of 4 broken sprites. |
| **Queue TV** *(lamp)* | off | A queue-line television. |
| **Jumping Fountain (Water/Snow)** *(fountain)* | off | Fountain spray type. |
| **Allowed on Queue** | on | May be placed on queue paths. |
| **Allowed on Slope** | on | May be placed on sloped paths. |

> Distinct vandalised/full art isn't authored in the add-on — those slots reuse
> the normal sprites. Supply `broken_meshes` / `full_meshes` via the CLI config
> for separate art.

**Scenery Group box** *(Type = Scenery Group)* — a tab; no geometry.

| Control | Default | What it does |
|---|---|---|
| **Priority** | int, default `40`, range `0–255` | Sort order of the tab (lower = earlier). |
| **Tab Icon** | *(none)* | Image datablock used as the tab icon; saved to PNG and palette-mapped on export. |
| **Member objects** | list | The object ids bundled under this tab. Use **＋ / －** to add/remove rows. |

**Custom Lighting box** (collapsible — click the header arrow) — geometry types only

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

### Panel: Selected Object → Scenery (per-object)

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
| **Wall Side** / **Banner Layer** *(walls & banners)* | Both/Front *(default)* / Front Only / Back Only | For a double-sided wall: which side this face belongs to ("Both" is shared). For a banner: **Back** = rear pole, **Front**/**Both** = front pole + sign. |
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
