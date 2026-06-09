"""
Blender PropertyGroups for the scenery add-on.
"""

import bpy
from bpy.props import (
    BoolProperty,
    BoolVectorProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Material, Object, PropertyGroup, Scene
from openrct2_object_common.blender.props import (
    SCALE_PRESET_ITEMS,
    SharedLight,
    scale_preset_update,
    simple_items,
    title,
)
from openrct2_scenery_generator.constants import DEFAULT_CURSOR, SMALL_SCENERY_SHAPES
from openrct2_x7_renderer.constants import TILE_SIZE


def _title(name: str) -> str:
    return title(name)


def _simple_items(names):
    return simple_items(names)


OBJECT_TYPE_ITEMS = [
    ("scenery_small", "Small Scenery", "Single-tile scenery (1 or 4 rotations)"),
    ("scenery_large", "Large Scenery", "Multi-tile scenery built from a tiles list"),
    ("scenery_wall", "Wall", "Single tile-edge wall panel (modelled along OBJ +Z)"),
    ("footpath_banner", "Banner", "Path-edge banner / sign (back pole + front sign per direction)"),
    ("footpath_item", "Path Addition", "Path addition: lamp, bin, bench, fountain, or queue TV"),
    ("scenery_group", "Scenery Group", "A scenery tab (name + icon + member ids); no geometry"),
]

PATH_ADDITION_RENDER_AS_ITEMS = [
    ("lamp", "Lamp", "Lamp post / queue TV (one upright per edge)"),
    ("bin", "Bin", "Litter bin (gains broken + full sprite blocks)"),
    ("bench", "Bench", "Seat facing the path (gains broken sprites when breakable)"),
    ("fountain", "Fountain", "Jumping fountain base"),
]

def _scale_preset_update(self, _context):
    scale_preset_update(self, _context)

# Per-material front/back role
WALL_SIDE_ITEMS = [
    ("BOTH", "Both / Front", "Shared: both wall sides, or a banner's front layer"),
    ("FRONT", "Front Only", "Front block of a double-sided wall, or a banner's front pole/sign"),
    ("BACK", "Back Only", "Rear block of a double-sided wall, or a banner's back pole"),
]

OBJECT_ROLE_ITEMS = [
    ("GEOMETRY", "Geometry", "Part of the scenery model"),
    ("IGNORE", "Ignore", "Not part of the scenery"),
]

SHAPE_ITEMS = [(s, s, "") for s in SMALL_SCENERY_SHAPES]

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

MATERIAL_REGION_ITEMS = [
    ("NONE", "None", "Plain shaded colour"),
    ("REMAP1", "Remap 1 (primary colour)", "Recoloured by the object's primary colour"),
    ("REMAP2", "Remap 2 (secondary)", "Recoloured by the secondary colour"),
    ("REMAP3", "Remap 3 (tertiary)", "Recoloured by the tertiary colour"),
    ("GREYSCALE", "Greyscale", "Greyscale shading region"),
    ("PEEP", "Peep", "Peep region"),
    ("CHAIN", "Chain", "Chain region"),
]


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
    # Phong shading controls
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
    # Wall-only classification
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


class VGSGroupEntry(PropertyGroup):
    """One member object id of a scenery group (tab)."""

    object_id: StringProperty(
        name="Object ID",
        description="An object id to include under this tab, e.g. author.scenery_small.obj",
        default="",
    )


class VGSTile(PropertyGroup):
    """One large-scenery tile."""

    x: IntProperty(name="X", description="Tile index along OBJ +X", default=0)
    y: IntProperty(name="Y", description="Tile index along OBJ +Z", default=0)
    z: IntProperty(name="Z", description="Height offset (coordinate units)", default=0)
    clearance: IntProperty(
        name="Clearance", description="Vertical clearance (coordinate units)", default=40, min=0
    )
    has_supports: BoolProperty(
        name="Supports",
        description="This tile draws vertical supports down to the ground",
        default=False,
    )
    allow_supports_above: BoolProperty(
        name="Supports Above",
        description="Allow another object's supports to rest on top of this tile",
        default=False,
    )
    # `corners`/`walls` are 4-bit masks in object.json
    corners: BoolVectorProperty(
        name="Quadrants",
        description="Which of the tile's 4 quadrants this piece occupies "
        "(drives selection / terrain clipping)",
        size=4,
        default=(True, True, True, True),
    )
    walls: BoolVectorProperty(
        name="Wall Edges",
        description="Which of the tile's 4 edges allow a wall against this piece",
        size=4,
        default=(False, False, False, False),
    )


VGSLight = SharedLight


class VGSScenerySettings(PropertyGroup):
    # Type & identity
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
        description="Unique id, e.g. openrct2sg.scenery_small.my_obj (avoid vanilla ids)",
        default="openrct2sg.scenery_small.my_object",
    )
    name: StringProperty(name="Name", default="My Scenery")
    authors: StringProperty(name="Authors", description="Comma-separated", default="")
    version: StringProperty(name="Version", default="1.0")

    # Common placement
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

    # Small scenery
    height: IntProperty(
        name="Height", description="Clearance in Z coordinate units (8 per step)", default=64, min=0
    )
    shape: EnumProperty(name="Shape", items=SHAPE_ITEMS, default="4/4")
    is_rotatable: BoolProperty(name="Rotatable", default=True)
    is_stackable: BoolProperty(name="Stackable", default=False)
    requires_flat_surface: BoolProperty(name="Requires Flat Surface", default=False)
    prohibit_walls: BoolProperty(name="Prohibit Walls", default=False)
    is_tree: BoolProperty(name="Tree", default=False)

    # Small-scenery animation
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

    # Large scenery
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

    # Wall
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
    is_opaque: BoolProperty(
        name="Opaque",
        description="Wall fully occludes the tile behind it (no see-through gaps)",
        default=False,
    )
    # Walls reuse is_animated as the plain isAnimated flag
    is_door: BoolProperty(
        name="Door",
        description="Wall is a door peeps and guests pass through",
        default=False,
    )
    is_long_door_animation: BoolProperty(
        name="Long Door Animation",
        description="Use the longer door open/close animation timing",
        default=False,
    )
    use_door_sound: BoolProperty(
        name="Custom Door Sound",
        description="Emit a doorSound id; off leaves it unset (engine default)",
        default=False,
    )
    door_sound: IntProperty(
        name="Door Sound",
        description="OpenRCT2 door sound id played when the door opens",
        default=1,
        min=0,
    )

    # Path addition
    render_as: EnumProperty(
        name="Render As",
        description="How the engine draws & indexes the path addition's sprites",
        items=PATH_ADDITION_RENDER_AS_ITEMS,
        default="lamp",
    )
    is_breakable: BoolProperty(
        name="Breakable",
        description="Can be vandalised; adds a block of 4 broken sprites (lamps/benches)",
        default=False,
    )
    is_television: BoolProperty(
        name="Queue TV",
        description="A queue-line television (drawn as a lamp)",
        default=False,
    )
    is_jumping_fountain_water: BoolProperty(name="Jumping Fountain (Water)", default=False)
    is_jumping_fountain_snow: BoolProperty(name="Jumping Fountain (Snow)", default=False)
    is_allowed_on_queue: BoolProperty(
        name="Allowed on Queue",
        description="May be placed on queue paths",
        default=True,
    )

    # Scenery group
    priority: IntProperty(
        name="Priority",
        description="Sort order of the tab in the scenery window (lower = earlier)",
        default=40,
        min=0,
        max=255,
    )
    entries: CollectionProperty(type=VGSGroupEntry)
    entry_index: IntProperty(default=0)
    icon: PointerProperty(
        name="Tab Icon",
        description="Image used as the group's tab icon (palette-mapped at export)",
        type=bpy.types.Image,
    )

    # Custom lighting
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
    VGSGroupEntry,
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
