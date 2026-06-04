"""Blender PropertyGroups for the scenery add-on.

Mirrors the config the core `build_small_scenery` / `build_large_scenery`
consume (see scene_to_scenery.py), expressed as native Blender properties so a
scenery object is authored entirely in the UI. Uses a `vgs_` prefix so this
add-on can coexist with the vehicle add-on (`vg_`).

NOTE: no ``from __future__ import annotations`` — PEP 563 would stringify the
``prop: SomeProperty(...)`` definitions and break Blender registration.
"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Material, Object, PropertyGroup, Scene
from openrct2_scenery_generator.constants import DEFAULT_CURSOR, SMALL_SCENERY_SHAPES
from openrct2_x7_renderer.constants import TILE_SIZE


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _simple_items(names):
    return [(n, _title(n), "") for n in names]


OBJECT_TYPE_ITEMS = [
    ("scenery_small", "Small Scenery", "Single-tile scenery (1 or 4 rotations)"),
    ("scenery_large", "Large Scenery", "Multi-tile scenery built from a tiles list"),
    ("scenery_wall", "Wall", "Single tile-edge wall panel (modelled along OBJ +Z)"),
]

# Render-scale presets (mirrors the vehicle add-on): how many OBJ units span one
# OpenRCT2 tile. Drives sprite size and the tile-anchor maths.
SCALE_PRESET_VALUES = {
    "REALISTIC": TILE_SIZE,
    "TILE": 1.0,
}
SCALE_PRESET_ITEMS = [
    ("REALISTIC", f"Realistic ({TILE_SIZE:g} m/tile)", "Match RCT2's real-world tile scale"),
    ("TILE", "1 unit = 1 tile", "Model in tiles: one OBJ unit spans one tile"),
    ("CUSTOM", "Custom", "Set the units-per-tile value manually"),
]


def _scale_preset_update(self, _context):
    """Write the preset's units-per-tile into the consumed value (Custom: no-op)."""
    value = SCALE_PRESET_VALUES.get(self.scale_preset)
    if value is not None:
        self.units_per_tile = value

# Per-material role on a double-sided wall. Mirrors the MTL name classification
# (*Front* / *Back*) the CLI path uses, exposed as an explicit picker. Untagged
# ("BOTH") faces are shared and appear on both sides.
WALL_SIDE_ITEMS = [
    ("BOTH", "Both Sides", "Shared face; appears on both sides of a double-sided wall"),
    ("FRONT", "Front Only", "Only on the front block of a double-sided wall"),
    ("BACK", "Back Only", "Only on the rear block of a double-sided wall"),
]

OBJECT_ROLE_ITEMS = [
    ("GEOMETRY", "Geometry", "Part of the scenery model"),
    ("IGNORE", "Ignore", "Not part of the scenery"),
]

SHAPE_ITEMS = [(s, s, "") for s in SMALL_SCENERY_SHAPES]

# The cursor identifiers OpenRCT2 accepts in an object.json `cursor` field
# (ObjectJsonHelpers cursor lookup table / CursorID enum). Anything outside this
# set is rejected by the engine, so a closed dropdown is safer than free text.
_CURSOR_NAMES = [
    "CURSOR_ARROW",
    "CURSOR_BLANK",
    "CURSOR_UP_ARROW",
    "CURSOR_UP_DOWN_ARROW",
    "CURSOR_HAND_POINT",
    "CURSOR_ZZZ",
    "CURSOR_DIAGONAL_ARROWS",
    "CURSOR_PICKER",
    "CURSOR_TREE_DOWN",
    "CURSOR_FOUNTAIN_DOWN",
    "CURSOR_STATUE_DOWN",
    "CURSOR_BENCH_DOWN",
    "CURSOR_CROSS_HAIR",
    "CURSOR_BIN_DOWN",
    "CURSOR_LAMPPOST_DOWN",
    "CURSOR_FENCE_DOWN",
    "CURSOR_FLOWER_DOWN",
    "CURSOR_PATH_DOWN",
    "CURSOR_DIG_DOWN",
    "CURSOR_WATER_DOWN",
    "CURSOR_HOUSE_DOWN",
    "CURSOR_VOLCANO_DOWN",
    "CURSOR_WALK_DOWN",
    "CURSOR_PAINT_DOWN",
    "CURSOR_ENTRANCE_DOWN",
    "CURSOR_HAND_OPEN",
    "CURSOR_HAND_CLOSED",
]
CURSOR_ITEMS = [(n, _title(n.removeprefix("CURSOR_")), "") for n in _CURSOR_NAMES]

# Same material-region scheme as the vehicle add-on; "NONE" is a plain colour,
# the REMAP* regions are recoloured by the placement colours.
MATERIAL_REGION_ITEMS = [
    ("NONE", "None", "Plain shaded colour"),
    ("REMAP1", "Remap 1 (primary colour)", "Recoloured by the object's primary colour"),
    ("REMAP2", "Remap 2 (secondary)", "Recoloured by the secondary colour"),
    ("REMAP3", "Remap 3 (tertiary)", "Recoloured by the tertiary colour"),
    ("GREYSCALE", "Greyscale", "Greyscale shading region"),
    ("PEEP", "Peep", "Peep region"),
    ("CHAIN", "Chain", "Chain region"),
]

LIGHT_TYPE_ITEMS = [
    ("diffuse", "Diffuse", "Directional diffuse light"),
    ("specular", "Specular", "Specular highlight light"),
]

# Animation cycle length = number of ticks the engine steps through before
# looping. The engine masks the tick counter with `mask = cycle - 1`, so the
# cycle MUST be a power of two for even playback (Paint.SmallScenery.cpp).
ANIMATION_CYCLE_ITEMS = [
    ("4", "4 frames", "Short loop"),
    ("8", "8 frames", "Medium loop"),
    ("16", "16 frames", "Long loop"),
    ("32", "32 frames", "Long loop (128 sprites)"),
    ("64", "64 frames", "Long loop (256 sprites)"),
    ("128", "128 frames", "Very long loop (512 sprites)"),
    ("256", "256 frames", "Very long loop (1024 sprites)"),
]

ANIMATION_LOOP_ITEMS = [
    ("LOOP", "Loop", "Play poses 0..N-1 then jump back to 0"),
    ("PINGPONG", "Ping-Pong", "Play poses forward then back (smooth for swings)"),
]

# How each animated object's geometry is sampled. The cheap default treats an
# object as a rigid body (one mesh + a per-pose transform), which can't capture
# armature/shape-key deformation. "Bake" re-extracts the deformed mesh at every
# pose -- needed for skinned/deforming objects, at the cost of one mesh per pose.
ANIMATION_DEFORM_ITEMS = [
    ("AUTO", "Auto", "Bake objects with an armature/deform modifier or animated "
     "shape keys; keep others rigid"),
    ("ALWAYS", "Bake all", "Re-extract every object's mesh each pose (use for "
     "deformation Auto can't detect)"),
    ("NEVER", "Rigid only", "Never re-extract; animate transforms only "
     "(deformation is frozen at the rest pose)"),
]


class VGSMaterialSettings(PropertyGroup):
    region: EnumProperty(
        name="Region",
        description="How OpenRCT2 treats this material's pixels",
        items=MATERIAL_REGION_ITEMS,
        default="NONE",
    )
    is_mask: BoolProperty(name="Mask", default=False)
    is_visible_mask: BoolProperty(name="Visible Mask", default=False)
    no_ao: BoolProperty(name="No Ambient Occlusion", default=False)
    edge: BoolProperty(name="Edge AA", default=False)
    dark_edge: BoolProperty(name="Dark Edge AA", default=False)
    no_bleed: BoolProperty(name="No Bleed", default=False)
    flat_shaded: BoolProperty(name="Flat Shaded", default=False)
    texture: PointerProperty(
        name="Texture",
        description="Optional image; must be saved to disk (its file is read at export)",
        type=bpy.types.Image,
    )
    # Phong shading controls, mirroring the vehicle add-on's VGMaterialSettings.
    # Specular is always taken from here; diffuse colour falls back to the
    # shader's Base Color unless overridden below (see scene_to_scenery).
    use_color_override: BoolProperty(
        name="Override Color",
        description="Use the color below instead of the shader's Base Color",
        default=False,
    )
    diffuse_color: FloatVectorProperty(
        name="Color",
        description="Flat diffuse color (used when Override Color is on)",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8),
    )
    specular_intensity: FloatProperty(
        name="Specular Intensity",
        description="Brightness of the specular highlight (scales the specular color)",
        default=0.5,
        min=0.0,
        soft_max=1.0,
    )
    specular_exponent: FloatProperty(
        name="Specular Exponent",
        description=(
            "Phong specular exponent: tightness of the highlight "
            "(higher = smaller, sharper)"
        ),
        default=50.0,
        min=1.0,
        soft_max=256.0,
    )
    use_specular_tint: BoolProperty(
        name="Tint Highlight",
        description="Tint the specular highlight with the color below (off = white)",
        default=False,
    )
    specular_tint: FloatVectorProperty(
        name="Specular Tint",
        description="Specular highlight color (used when Tint Highlight is on)",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
    )
    # Wall-only classification. These replace the MTL *Glass* / *Front* / *Back*
    # name rules for the add-on path; they only matter when the object type is a
    # wall (see scene_to_scenery._material_from_bpy).
    is_glass: BoolProperty(
        name="Glass",
        description="Translucent glass pane; split into the wall's glass overlay block",
        default=False,
    )
    wall_side: EnumProperty(
        name="Wall Side",
        description="Which side of a double-sided wall this face belongs to",
        items=WALL_SIDE_ITEMS,
        default="BOTH",
    )


class VGSObjectSettings(PropertyGroup):
    role: EnumProperty(
        name="Role",
        description="Whether this object is part of the scenery model",
        items=OBJECT_ROLE_ITEMS,
        default="GEOMETRY",
    )


class VGSTile(PropertyGroup):
    """One large-scenery tile. x/y are tile indices (the exporter converts to
    OpenRCT2 coordinate units); z/clearance are in coordinate units."""

    x: IntProperty(name="X", description="Tile index along OBJ +X", default=0)
    y: IntProperty(name="Y", description="Tile index along OBJ +Z", default=0)
    z: IntProperty(name="Z", description="Height offset (coordinate units)", default=0)
    clearance: IntProperty(
        name="Clearance", description="Vertical clearance (coordinate units)", default=40, min=0
    )


class VGSLight(PropertyGroup):
    type: EnumProperty(name="Type", items=LIGHT_TYPE_ITEMS, default="diffuse")
    shadow: BoolProperty(name="Casts Shadow", default=False)
    direction: FloatVectorProperty(
        name="Direction",
        description="Direction in OBJ space (+X forward, +Y up, +Z right); normalized at render",
        size=3,
        default=(0.0, 1.0, 0.0),
        subtype="XYZ",
    )
    strength: FloatProperty(name="Strength", default=0.5, min=0.0)


class VGSScenerySettings(PropertyGroup):
    # --- Type & identity ---------------------------------------------------
    object_type: EnumProperty(name="Type", items=OBJECT_TYPE_ITEMS, default="scenery_small")
    scale_preset: EnumProperty(
        name="Scale",
        description="How many OBJ units map to one OpenRCT2 tile",
        items=SCALE_PRESET_ITEMS,
        default="REALISTIC",
        update=_scale_preset_update,
    )
    units_per_tile: FloatProperty(
        name="Units / Tile",
        description=(
            "OBJ units per OpenRCT2 tile. Drives sprite size and the tile-anchor "
            "maths for large scenery and walls."
        ),
        default=TILE_SIZE,
        min=0.01,
        soft_max=16.0,
    )
    id: StringProperty(
        name="Object ID",
        description="Unique id, e.g. openrct2vg.scenery_small.my_obj (avoid vanilla ids)",
        default="openrct2vg.scenery_small.my_object",
    )
    name: StringProperty(name="Name", default="My Scenery")
    authors: StringProperty(name="Authors", description="Comma-separated", default="")
    version: StringProperty(name="Version", default="1.0")
    preview: StringProperty(
        name="Preview Image", description="Path to a preview image", subtype="FILE_PATH", default=""
    )

    # --- Common placement --------------------------------------------------
    price: FloatProperty(name="Price", default=2.0)
    removal_price: FloatProperty(name="Removal Price", default=1.0)
    cursor: EnumProperty(
        name="Cursor",
        description="Mouse cursor shown while placing the object",
        items=CURSOR_ITEMS,
        default=DEFAULT_CURSOR,
    )
    scenery_group: StringProperty(
        name="Scenery Group", description="Optional scenery-group object id", default=""
    )
    has_primary_colour: BoolProperty(
        name="Primary Colour",
        description="Recolourable; pairs with Remap 1 materials",
        default=False,
    )
    has_secondary_colour: BoolProperty(name="Secondary Colour", default=False)

    # --- Small scenery -----------------------------------------------------
    height: IntProperty(
        name="Height", description="Clearance in Z coordinate units (8 per step)", default=64, min=0
    )
    shape: EnumProperty(name="Shape", items=SHAPE_ITEMS, default="4/4")
    is_rotatable: BoolProperty(name="Rotatable", default=True)
    is_stackable: BoolProperty(name="Stackable", default=False)
    requires_flat_surface: BoolProperty(name="Requires Flat Surface", default=False)
    prohibit_walls: BoolProperty(name="Prohibit Walls", default=False)
    is_tree: BoolProperty(name="Tree", default=False)

    # --- Small-scenery animation (samples Blender keyframes into poses) -----
    is_animated: BoolProperty(
        name="Animated",
        description="Sample the scene's keyframes into animation poses",
        default=False,
    )
    animation_cycle: EnumProperty(
        name="Cycle",
        description="Number of animation steps before looping (power of two)",
        items=ANIMATION_CYCLE_ITEMS,
        default="8",
    )
    animation_loop: EnumProperty(
        name="Playback", items=ANIMATION_LOOP_ITEMS, default="LOOP"
    )
    animation_delay: IntProperty(
        name="Speed (delay)",
        description="Tick bit-shift; higher = slower animation",
        default=1,
        min=0,
        max=15,
    )
    anim_start_frame: IntProperty(
        name="Start Frame",
        description="First scene frame to sample (uses scene range if end <= start)",
        default=1,
    )
    anim_end_frame: IntProperty(name="End Frame", default=24)
    animation_deform: EnumProperty(
        name="Deformation",
        description="How animated geometry is sampled (rigid transform vs. "
        "re-extracting the deformed mesh per pose)",
        items=ANIMATION_DEFORM_ITEMS,
        default="AUTO",
    )

    # --- Large scenery -----------------------------------------------------
    has_tertiary_colour: BoolProperty(name="Tertiary Colour", default=False)
    is_photogenic: BoolProperty(name="Photogenic", default=False)
    scrolling_mode: IntProperty(
        name="Scrolling Mode",
        description="255 = none. Only set for scrolling signs.",
        default=255,
        min=0,
        max=255,
    )
    tiles: CollectionProperty(type=VGSTile)
    tile_index: IntProperty(default=0)

    # --- Wall --------------------------------------------------------------
    # `wall_height` is in wall height units; the engine renders it `* 8`
    # coordinate units tall (separate from small scenery's `height` clearance).
    wall_height: IntProperty(
        name="Height",
        description="Wall height in wall units (rendered height * 8 coordinate units)",
        default=2,
        min=1,
    )
    is_allowed_on_slope: BoolProperty(
        name="Allowed on Slope",
        description="Can be placed on sloped terrain (adds the 4 slope sprites)",
        default=True,
    )
    has_glass: BoolProperty(
        name="Has Glass",
        description="Wall has translucent glass panes (materials marked Glass)",
        default=False,
    )
    is_double_sided: BoolProperty(
        name="Double-Sided",
        description="Distinct front/back faces (materials marked Front/Back); rear block at +6",
        default=False,
    )

    # --- Custom lighting ---------------------------------------------------
    lights: CollectionProperty(type=VGSLight)
    light_index: IntProperty(default=0)
    show_lights: BoolProperty(
        name="Custom Lighting",
        description="Override the default lighting rig with a custom one",
        default=False,
    )


_CLASSES = (
    VGSMaterialSettings,
    VGSObjectSettings,
    VGSTile,
    VGSLight,
    VGSScenerySettings,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    Scene.vgs_scenery = PointerProperty(type=VGSScenerySettings)
    Object.vgs_object = PointerProperty(type=VGSObjectSettings)
    Material.vgs_material = PointerProperty(type=VGSMaterialSettings)


def unregister():
    del Material.vgs_material
    del Object.vgs_object
    del Scene.vgs_scenery
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
