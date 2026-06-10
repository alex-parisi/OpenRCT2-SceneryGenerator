"""
UI panels for the scenery add-on: scene settings (3D View N-panel) +
per-object role + per-material region."""

import bpy
from bpy.types import Panel, UIList
from openrct2_scenery_generator.constants import WALL_ANIMATION_FRAMES


class VGS_UL_tiles(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="MESH_PLANE")
        row.prop(item, "x", text="X")
        row.prop(item, "y", text="Y")
        row.prop(item, "clearance", text="Clr")


class VGS_UL_lights(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="LIGHT")
        row.prop(item, "type", text="")
        row.prop(item, "strength", text="")


class VGS_UL_group_entries(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="OBJECT_DATA")
        row.prop(item, "object_id", text="", emboss=False)


class VGS_PT_scenery(Panel):
    bl_label = "OpenRCT2 Scenery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"

    def draw(self, context):
        layout = self.layout
        ss = context.scene.vgs_scenery
        is_group = ss.object_type == "scenery_group"

        layout.prop(ss, "object_type")
        if not is_group:
            layout.prop(ss, "scale_preset")
            if ss.scale_preset == "CUSTOM":
                layout.prop(ss, "units_per_tile")

        box = layout.box()
        box.label(text="Identity", icon="INFO")
        box.prop(ss, "id")
        box.prop(ss, "name")
        box.prop(ss, "authors")
        box.prop(ss, "version")

        if is_group:
            _draw_group(layout, ss)
            _draw_actions(layout)
            return

        _draw_placement(layout, ss)

        if ss.object_type == "scenery_small":
            box = layout.box()
            box.label(text="Small Scenery", icon="MESH_CUBE")
            box.prop(ss, "shape")
            box.prop(ss, "height")
            col = box.column(align=True)
            col.prop(ss, "is_rotatable")
            col.prop(ss, "is_stackable")
            col.prop(ss, "requires_flat_surface")
            col.prop(ss, "prohibit_walls")
            col.prop(ss, "is_tree")

            abox = layout.box()
            abox.prop(ss, "is_animated", icon="ANIM")
            if ss.is_animated:
                abox.prop(ss, "animation_cycle")
                abox.prop(ss, "animation_loop")
                abox.prop(ss, "animation_delay")
                abox.prop(ss, "animation_deform")
                row = abox.row(align=True)
                row.prop(ss, "anim_start_frame")
                row.prop(ss, "anim_end_frame")
                abox.label(text="Keyframe the geometry over this range.", icon="INFO")
                if ss.animation_deform != "NEVER":
                    abox.label(
                        text="Deforming objects: one mesh baked per pose.",
                        icon="INFO",
                    )
        elif ss.object_type == "scenery_wall":
            box = layout.box()
            box.label(text="Wall", icon="MOD_BUILD")
            box.prop(ss, "wall_height")

            wall_animated = ss.is_animated and not ss.is_door
            col = box.column(align=True)
            sub = col.column(align=True)
            sub.enabled = not wall_animated
            sub.prop(ss, "is_allowed_on_slope")
            sub.prop(ss, "has_glass")
            sub.prop(ss, "is_double_sided")
            col.prop(ss, "has_tertiary_colour")
            col.prop(ss, "is_opaque")
            if ss.has_glass and ss.is_double_sided and not wall_animated:
                box.label(
                    text="Glass + double-sided isn't supported; double-sided is dropped.",
                    icon="ERROR",
                )

            if not ss.is_animated:
                dbox = box.box()
                dbox.prop(ss, "is_door", icon="MOD_BEVEL")
                if ss.is_door:
                    dbox.prop(ss, "is_long_door_animation")
                    row = dbox.row(align=True)
                    row.prop(ss, "use_door_sound", text="")
                    dsub = row.row()
                    dsub.enabled = ss.use_door_sound
                    dsub.prop(ss, "door_sound")
                    dbox.prop(ss, "animation_deform")
                    row = dbox.row(align=True)
                    row.prop(ss, "anim_start_frame")
                    row.prop(ss, "anim_end_frame")
                    dbox.label(
                        text="Keyframe the leaf swinging open over this range;",
                        icon="INFO",
                    )
                    dbox.label(text="the backward swing is mirrored automatically.")

            if not ss.is_door:
                abox = box.box()
                abox.prop(ss, "is_animated", icon="ANIM")
                if ss.is_animated:
                    abox.prop(ss, "animation_deform")
                    row = abox.row(align=True)
                    row.prop(ss, "anim_start_frame")
                    row.prop(ss, "anim_end_frame")
                    abox.label(
                        text=f"Flat-only; {WALL_ANIMATION_FRAMES} frames sampled "
                        "over this range.",
                        icon="INFO",
                    )

            box.label(text="Model the panel running along OBJ +Z.", icon="INFO")
        elif ss.object_type == "footpath_banner":
            box = layout.box()
            box.label(text="Banner", icon="MOD_LENGTH")
            box.prop(ss, "scrolling_mode")
            box.label(text="Tag the sign material Front and the back pole Back.", icon="INFO")
            box.label(text="Primary Colour recolours a Remap 1 sign.", icon="INFO")
        elif ss.object_type == "footpath_item":
            box = layout.box()
            box.label(text="Path Addition", icon="OUTLINER_OB_LIGHT")
            box.prop(ss, "render_as")
            col = box.column(align=True)
            if ss.render_as in ("lamp", "bench"):
                col.prop(ss, "is_breakable")
            if ss.render_as == "lamp":
                col.prop(ss, "is_television")
            if ss.render_as == "fountain":
                col.prop(ss, "is_jumping_fountain_water")
                col.prop(ss, "is_jumping_fountain_snow")
            col.prop(ss, "is_allowed_on_queue")
            col.prop(ss, "is_allowed_on_slope")
            box.label(text="Model the item centred on the tile origin.", icon="INFO")
            box.label(text="Broken/full states reuse the normal sprites.", icon="INFO")
        else:
            box = layout.box()
            box.label(text="Large Scenery", icon="MESH_GRID")
            col = box.column(align=True)
            col.prop(ss, "has_tertiary_colour")
            col.prop(ss, "is_photogenic")
            box.prop(ss, "scrolling_mode")
            box.label(text="Tiles (x/y are tile indices):")
            row = box.row()
            row.template_list("VGS_UL_tiles", "", ss, "tiles", ss, "tile_index", rows=3)
            colb = row.column(align=True)
            colb.operator("vgs.tile_add", icon="ADD", text="")
            colb.operator("vgs.tile_remove", icon="REMOVE", text="")
            if ss.tiles:
                t = ss.tiles[ss.tile_index]
                sub = box.column(align=True)
                rr = sub.row(align=True)
                rr.prop(t, "x")
                rr.prop(t, "y")
                rr = sub.row(align=True)
                rr.prop(t, "z")
                rr.prop(t, "clearance")
                rr = sub.row(align=True)
                rr.prop(t, "has_supports", toggle=True)
                rr.prop(t, "allow_supports_above", toggle=True)
                sub.label(text="Occupied quadrants:")
                sub.row(align=True).prop(t, "corners", text="")
                sub.label(text="Wall edges:")
                sub.row(align=True).prop(t, "walls", text="")
            else:
                box.label(text="No tiles - add at least one.", icon="ERROR")

        _draw_lights(layout, ss)
        _draw_actions(layout)


def _draw_placement(layout, ss):
    """Pricing / cursor / colours, tailored per type."""
    box = layout.box()
    box.label(text="Placement", icon="TOOL_SETTINGS")
    ot = ss.object_type
    if ot == "footpath_banner":
        box.prop(ss, "price")
        box.prop(ss, "scenery_group")
        box.prop(ss, "has_primary_colour")
        return
    if ot == "footpath_item":
        box.prop(ss, "price")
        box.prop(ss, "cursor")
        box.prop(ss, "scenery_group")
        return
    row = box.row(align=True)
    row.prop(ss, "price")
    row.prop(ss, "removal_price")
    box.prop(ss, "cursor")
    box.prop(ss, "scenery_group")
    box.prop(ss, "has_primary_colour")
    box.prop(ss, "has_secondary_colour")
    if ot == "scenery_small":
        box.prop(ss, "has_tertiary_colour")


def _draw_group(layout, ss):
    """The scenery-group tab"""
    box = layout.box()
    box.label(text="Scenery Group", icon="GROUP")
    box.prop(ss, "priority")
    box.prop(ss, "icon")
    box.label(text="Member objects:")
    row = box.row()
    row.template_list("VGS_UL_group_entries", "", ss, "entries", ss, "entry_index", rows=4)
    col = row.column(align=True)
    col.operator("vgs.entry_add", icon="ADD", text="")
    col.operator("vgs.entry_remove", icon="REMOVE", text="")
    if not ss.entries:
        box.label(text="No members - add the object ids in this tab.", icon="INFO")


def _draw_lights(layout, ss):
    box = layout.box()
    row = box.row()
    row.prop(
        ss, "show_lights",
        icon="TRIA_DOWN" if ss.show_lights else "TRIA_RIGHT", emboss=False,
    )
    row.label(text="", icon="LIGHT_SUN")
    if ss.show_lights:
        row = box.row()
        row.template_list("VGS_UL_lights", "", ss, "lights", ss, "light_index", rows=3)
        col = row.column(align=True)
        col.operator("vgs.light_add", icon="ADD", text="")
        col.operator("vgs.light_remove", icon="REMOVE", text="")
        if ss.lights:
            light = ss.lights[ss.light_index]
            sub = box.column()
            sub.prop(light, "type")
            sub.prop(light, "shadow")
            sub.prop(light, "direction")
            sub.prop(light, "strength")
        else:
            box.label(text="No lights - using the default rig.", icon="INFO")


def _draw_actions(layout):
    col = layout.column(align=True)
    col.scale_y = 1.3
    col.operator("vgs.test_render", icon="RENDER_STILL")
    col.operator("vgs.export_parkobj", icon="EXPORT")


def _draw_material_settings(layout, ms, object_type):
    """Draw a material's OpenRCT2 region/flags/shading settings."""
    if object_type == "scenery_wall":
        col = layout.column(align=True)
        col.prop(ms, "is_glass")
        col.prop(ms, "wall_side")
    elif object_type == "footpath_banner":
        layout.prop(ms, "wall_side", text="Banner Layer")
    layout.prop(ms, "region")
    col = layout.column(align=True)
    col.prop(ms, "is_mask")
    col.prop(ms, "is_visible_mask")
    col.prop(ms, "no_ao")
    col.prop(ms, "edge")
    col.prop(ms, "dark_edge")
    col.prop(ms, "no_bleed")
    layout.prop(ms, "texture")

    col = layout.column(align=True)
    col.label(text="Shading")
    row = col.row(align=True)
    row.prop(ms, "use_color_override", text="")
    sub = row.row()
    sub.enabled = ms.use_color_override
    sub.prop(ms, "diffuse_color", text="Color")
    col.prop(ms, "specular_exponent")
    col.prop(ms, "specular_intensity")
    row = col.row(align=True)
    row.prop(ms, "use_specular_tint", text="")
    sub = row.row()
    sub.enabled = ms.use_specular_tint
    sub.prop(ms, "specular_tint", text="Specular Tint")


def _draw_object_settings(layout, obj, object_type):
    """Draw the active object's role and its materials, folded together so a
    scenery part is authored from the viewport sidebar without leaving it."""
    layout.prop(obj.vgs_object, "role")
    if obj.vgs_object.role == "IGNORE":
        return

    box = layout.box()
    box.label(text="Materials", icon="MATERIAL")
    if not obj.material_slots:
        box.label(text="No materials on this object.", icon="INFO")
        return
    if len(obj.material_slots) > 1:
        box.template_list(
            "MATERIAL_UL_matslots", "", obj, "material_slots",
            obj, "active_material_index", rows=2,
        )
    mat = obj.active_material
    if mat is None:
        box.label(text="Empty material slot.", icon="INFO")
    else:
        _draw_material_settings(box, mat.vgs_material, object_type)


# Shared "Selected Object" container
_SHARED_PARENT_IDNAME = "OPENRCT2_PT_selected_object"


class OPENRCT2_PT_selected_object(Panel):
    bl_idname = _SHARED_PARENT_IDNAME
    bl_label = "Selected Object"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        pass


def _register_shared_parent():
    """Register the shared parent unless another add-on already did."""
    if not hasattr(bpy.types, _SHARED_PARENT_IDNAME):
        bpy.utils.register_class(OPENRCT2_PT_selected_object)


def _unregister_shared_parent():
    """Drop the shared parent only once no add-on's child still nests under it."""
    cls = getattr(bpy.types, _SHARED_PARENT_IDNAME, None)
    if cls is None:
        return
    for name in dir(bpy.types):
        if getattr(getattr(bpy.types, name, None), "bl_parent_id", "") == _SHARED_PARENT_IDNAME:
            return
    bpy.utils.unregister_class(cls)


class VGS_PT_object_view3d(Panel):
    """The active object's scenery settings, as a child of "Selected Object"."""

    bl_label = "Scenery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"
    bl_parent_id = _SHARED_PARENT_IDNAME
    bl_order = 1

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and hasattr(obj, "vgs_object")

    def draw(self, context):
        _draw_object_settings(
            self.layout, context.object, context.scene.vgs_scenery.object_type
        )


_CLASSES = (
    VGS_UL_tiles,
    VGS_UL_lights,
    VGS_UL_group_entries,
    VGS_PT_scenery,
    VGS_PT_object_view3d,
)


def register():
    _register_shared_parent()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _unregister_shared_parent()
