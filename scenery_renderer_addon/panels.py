"""UI panels for the scenery add-on: scene settings (3D View N-panel) +
per-object role + per-material region."""

import bpy
from bpy.types import Panel, UIList


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


class VGS_PT_scenery(Panel):
    bl_label = "OpenRCT2 Scenery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"

    def draw(self, context):
        layout = self.layout
        ss = context.scene.vgs_scenery

        layout.prop(ss, "object_type")
        layout.prop(ss, "scale_preset")
        if ss.scale_preset == "CUSTOM":
            layout.prop(ss, "units_per_tile")

        box = layout.box()
        box.label(text="Identity", icon="INFO")
        box.prop(ss, "id")
        box.prop(ss, "name")
        box.prop(ss, "authors")
        box.prop(ss, "version")

        box = layout.box()
        box.label(text="Placement", icon="TOOL_SETTINGS")
        row = box.row(align=True)
        row.prop(ss, "price")
        row.prop(ss, "removal_price")
        box.prop(ss, "cursor")
        box.prop(ss, "scenery_group")
        box.prop(ss, "has_primary_colour")
        box.prop(ss, "has_secondary_colour")

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
            col = box.column(align=True)
            col.prop(ss, "is_allowed_on_slope")
            col.prop(ss, "has_glass")
            col.prop(ss, "is_double_sided")
            col.prop(ss, "has_tertiary_colour")
            if ss.has_glass and ss.is_double_sided:
                box.label(
                    text="Glass + double-sided isn't supported; double-sided is dropped.",
                    icon="ERROR",
                )
            box.label(text="Model the panel running along OBJ +Z.", icon="INFO")
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
            else:
                box.label(text="No tiles - add at least one.", icon="ERROR")

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

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("vgs.test_render", icon="RENDER_STILL")
        col.operator("vgs.export_parkobj", icon="EXPORT")


def _draw_material_settings(layout, ms, object_type):
    """Draw a material's OpenRCT2 region/flags/shading settings.

    Mirrors the vehicle add-on's per-material controls so the settings can live
    inline in the "Selected Object" panel instead of the Material Properties tab.
    The wall-only glass/side classification shows only for wall objects.
    """
    if object_type == "scenery_wall":
        col = layout.column(align=True)
        col.prop(ms, "is_glass")
        col.prop(ms, "wall_side")
    layout.prop(ms, "region")
    col = layout.column(align=True)
    col.prop(ms, "is_mask")
    col.prop(ms, "is_visible_mask")
    col.prop(ms, "no_ao")
    col.prop(ms, "edge")
    col.prop(ms, "dark_edge")
    col.prop(ms, "no_bleed")
    col.prop(ms, "flat_shaded")
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


# --- Shared "Selected Object" container -------------------------------------
# The vehicle and scenery add-ons each ship an identical copy of this trivial
# parent panel and register it cooperatively (guarded by idname) so a single
# "Selected Object" panel hosts whichever add-ons are installed. Each add-on
# contributes a child sub-panel via ``bl_parent_id``; this parent owns only the
# header. The two copies MUST keep the same ``bl_idname``.
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
    """Drop the shared parent only once no add-on's child still nests under it.

    Call this *after* unregistering this add-on's own child panels, so the
    scan below sees only the other add-on's remaining children.
    """
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
