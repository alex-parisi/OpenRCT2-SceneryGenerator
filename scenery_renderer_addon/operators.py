"""
Blender operators for the scenery add-on: test render, threaded export,
and tile/light list management.
"""

import os
import tempfile
import time

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from openrct2_object_common.blender.lights import lights_from_items
from openrct2_object_common.blender.modal import RenderModalBase
from openrct2_object_common.cli import make_context
from openrct2_scenery_generator.exporter import (
    export_banner_test,
    export_banner_to,
    export_large_scenery_test,
    export_large_scenery_to,
    export_path_addition_test,
    export_path_addition_to,
    export_scenery_group_test,
    export_scenery_group_to,
    export_small_scenery_test,
    export_small_scenery_to,
    export_wall_scenery_test,
    export_wall_scenery_to,
)
from openrct2_scenery_generator.loader import (
    build_banner,
    build_large_scenery,
    build_path_addition,
    build_small_scenery,
    build_wall_scenery,
)

from . import scene_to_scenery

_EXPORTERS = {
    "small": (export_small_scenery_to, export_small_scenery_test),
    "large": (export_large_scenery_to, export_large_scenery_test),
    "wall": (export_wall_scenery_to, export_wall_scenery_test),
    "banner": (export_banner_to, export_banner_test),
    "item": (export_path_addition_to, export_path_addition_test),
    "group": (export_scenery_group_to, export_scenery_group_test),
}


def _build_scenery_from_scene(context):
    """Main-thread step: read bpy data into a scenery object + its kind."""
    if context.scene.vgs_scenery.object_type == "scenery_group":
        return "group", scene_to_scenery.build_group(context)
    config, meshes = scene_to_scenery.build_config_and_meshes(context)
    obj_type = config["object_type"]
    if obj_type == "scenery_large":
        return "large", build_large_scenery(config, meshes)
    if obj_type == "scenery_wall":
        return "wall", build_wall_scenery(config, meshes)
    if obj_type == "footpath_banner":
        return "banner", build_banner(config, meshes)
    if obj_type == "footpath_item":
        return "item", build_path_addition(config, meshes)
    return "small", build_small_scenery(config, meshes)


class _SceneryModalBase(RenderModalBase):
    """Shared base for the scenery render operators."""

    _clean_error_types = (scene_to_scenery.SceneError,)
    _invalid_prefix = "Invalid scenery"

    def _build(self, context):
        return _build_scenery_from_scene(context)

    def _prepare(self, context, payload) -> None:
        self._lights = lights_from_items(context.scene.vgs_scenery.lights)


class VGS_OT_test_render(_SceneryModalBase):
    bl_idname = "vgs.test_render"
    bl_label = "Test Render"
    bl_description = "Render the scenery quickly and show it in the Image Editor"

    _status_verb = "Rendering test"

    def _prepare(self, context, payload) -> None:
        super()._prepare(context, payload)
        self._tmp = tempfile.mkdtemp(prefix="vgs_test_")
        self._png = None

    def _render(self, payload) -> None:
        kind, obj = payload
        # Render at the real in-game scale
        ctx = make_context(self._lights, obj.units_per_tile, False)
        _EXPORTERS[kind][1](obj, ctx, self._tmp)
        # Every kind writes a combined contact sheet
        self._png = os.path.join(self._tmp, "preview_combined.png")

    def _on_success(self, context):
        if not self._png or not os.path.exists(self._png):
            self.report({"WARNING"}, "Render produced no sprite")
            return {"CANCELLED"}
        img = bpy.data.images.load(self._png, check_existing=False)
        for area in context.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                break
        self.report({"INFO"}, f"Test sprite loaded: {img.name}")
        return {"FINISHED"}


class VGS_OT_export_parkobj(_SceneryModalBase):
    bl_idname = "vgs.export_parkobj"
    bl_label = "Export .parkobj"
    bl_description = "Render every sprite and write an OpenRCT2 scenery .parkobj"

    _status_verb = "Exporting .parkobj"

    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext = ".parkobj"
    filter_glob: StringProperty(default="*.parkobj", options={"HIDDEN"})

    def invoke(self, context, event):
        ss = context.scene.vgs_scenery
        if not self.filepath:
            base = (ss.id or "scenery").replace("/", "_")
            self.filepath = bpy.path.ensure_ext(base, ".parkobj")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _prepare(self, context, payload) -> None:
        super()._prepare(context, payload)
        self._parkobj = bpy.path.abspath(self.filepath)
        self._work = tempfile.mkdtemp(prefix="vgs_export_")

    def _render(self, payload) -> None:
        kind, obj = payload
        ctx = make_context(self._lights, obj.units_per_tile, False)
        _EXPORTERS[kind][0](obj, ctx, self._parkobj, self._work)

    def _on_success(self, context):
        elapsed = int(time.monotonic() - self._start_time)
        build = f" (build {self._build_secs}s)" if self._build_secs else ""
        name = os.path.basename(self._parkobj)
        self.report({"INFO"}, f"Exported {name} in {elapsed}s{build}")
        return {"FINISHED"}


class VGS_OT_tile_add(Operator):
    bl_idname = "vgs.tile_add"
    bl_label = "Add Tile"
    bl_description = "Add a tile to the large-scenery footprint"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        ss.tiles.add()
        ss.tile_index = len(ss.tiles) - 1
        return {"FINISHED"}


class VGS_OT_tile_remove(Operator):
    bl_idname = "vgs.tile_remove"
    bl_label = "Remove Tile"
    bl_description = "Remove the selected tile"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        if not ss.tiles:
            return {"CANCELLED"}
        ss.tiles.remove(ss.tile_index)
        ss.tile_index = max(0, min(ss.tile_index, len(ss.tiles) - 1))
        return {"FINISHED"}


class VGS_OT_entry_add(Operator):
    bl_idname = "vgs.entry_add"
    bl_label = "Add Entry"
    bl_description = "Add a member object id to the scenery group"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        ss.entries.add()
        ss.entry_index = len(ss.entries) - 1
        return {"FINISHED"}


class VGS_OT_entry_remove(Operator):
    bl_idname = "vgs.entry_remove"
    bl_label = "Remove Entry"
    bl_description = "Remove the selected member object id"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        if not ss.entries:
            return {"CANCELLED"}
        ss.entries.remove(ss.entry_index)
        ss.entry_index = max(0, min(ss.entry_index, len(ss.entries) - 1))
        return {"FINISHED"}


class VGS_OT_light_add(Operator):
    bl_idname = "vgs.light_add"
    bl_label = "Add Light"
    bl_description = "Add a light to the custom lighting rig"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        ss.lights.add()
        ss.light_index = len(ss.lights) - 1
        return {"FINISHED"}


class VGS_OT_light_remove(Operator):
    bl_idname = "vgs.light_remove"
    bl_label = "Remove Light"
    bl_description = "Remove the selected light"

    def execute(self, context):
        ss = context.scene.vgs_scenery
        if not ss.lights:
            return {"CANCELLED"}
        ss.lights.remove(ss.light_index)
        ss.light_index = max(0, min(ss.light_index, len(ss.lights) - 1))
        return {"FINISHED"}


_CLASSES = (
    VGS_OT_test_render,
    VGS_OT_export_parkobj,
    VGS_OT_tile_add,
    VGS_OT_tile_remove,
    VGS_OT_entry_add,
    VGS_OT_entry_remove,
    VGS_OT_light_add,
    VGS_OT_light_remove,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
