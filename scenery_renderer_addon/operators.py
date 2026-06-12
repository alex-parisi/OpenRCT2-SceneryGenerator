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


def _build_one(
    context,
    *,
    ss=None,
    objects=None,
    offset=(0.0, 0.0, 0.0),
    shared=None,
    group_entries=(),
):
    """Main-thread step: read bpy data into a scenery object + its kind.

    With no keyword arguments this builds the whole scene from
    ``scene.vgs_scenery`` (single-object mode); a batch entry passes its own
    settings/objects/offset plus the scene settings as ``shared`` and, for a
    group with "Include All Batch Objects" on, its sibling ids as
    ``group_entries``.
    """
    if ss is None:
        ss = context.scene.vgs_scenery
    if ss.object_type == "scenery_group":
        return "group", scene_to_scenery.build_group(
            context, ss=ss, shared=shared, auto_entries=group_entries
        )
    config, meshes = scene_to_scenery.build_config_and_meshes(
        context, ss=ss, objects=objects, offset=offset, shared=shared
    )
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


def active_batch_entry(context):
    """The selected batch entry, or None when batch mode is off or empty."""
    bs = context.scene.vgs_batch
    if not (bs.enabled and bs.entries):
        return None
    return bs.entries[min(bs.index, len(bs.entries) - 1)]


def active_settings(context):
    """The settings being edited: the active batch entry's in batch mode,
    otherwise the scene's."""
    entry = active_batch_entry(context)
    return context.scene.vgs_scenery if entry is None else entry.settings


def _batch_member_ids(context, group_entry):
    """Ids of every non-group batch entry except ``group_entry`` itself, in
    list order — the auto-filled membership of a batch scenery group."""
    return [
        e.settings.id.strip()
        for e in context.scene.vgs_batch.entries
        if e.as_pointer() != group_entry.as_pointer()
        and e.settings.object_type != "scenery_group"
        and e.settings.id.strip()
    ]


def _build_entry(context, entry):
    """Build one batch entry, prefixing build errors with the entry's name."""
    label = entry.name or entry.settings.id or "unnamed"
    is_group = entry.settings.object_type == "scenery_group"
    if not is_group and entry.collection is None:
        raise scene_to_scenery.SceneError(
            f"Batch object '{label}': no Collection assigned."
        )
    objects = [] if entry.collection is None else entry.collection.all_objects
    group_entries = ()
    if is_group and entry.settings.entries_from_batch:
        group_entries = _batch_member_ids(context, entry)
    try:
        return _build_one(
            context,
            ss=entry.settings,
            objects=objects,
            offset=tuple(entry.offset),
            shared=context.scene.vgs_scenery,
            group_entries=group_entries,
        )
    except scene_to_scenery.SceneError as e:
        raise scene_to_scenery.SceneError(f"Batch object '{label}': {e}") from e


def _parkobj_filename(object_id: str) -> str:
    return (object_id or "scenery").replace("/", "_") + ".parkobj"


def _copy_props(src, dst) -> None:
    """Deep-copy a PropertyGroup's properties (seeds a new batch entry's
    settings from the selected entry or the single-object settings)."""
    for prop in src.bl_rna.properties:
        ident = prop.identifier
        if ident == "rna_type":
            continue
        if prop.type == "POINTER":
            value = getattr(src, ident)
            if isinstance(value, bpy.types.PropertyGroup):
                _copy_props(value, getattr(dst, ident))
            else:
                # ID datablock pointer (e.g. an Image): share the reference.
                setattr(dst, ident, value)
        elif prop.type == "COLLECTION":
            dst_coll = getattr(dst, ident)
            dst_coll.clear()
            for item in getattr(src, ident):
                _copy_props(item, dst_coll.add())
        elif not prop.is_readonly:
            value = getattr(src, ident)
            if getattr(prop, "is_array", False):
                value = tuple(value)
            setattr(dst, ident, value)


class _SceneryModalBase(RenderModalBase):
    """Shared base for the scenery render operators."""

    _clean_error_types = (scene_to_scenery.SceneError,)
    _invalid_prefix = "Invalid scenery"

    def _build(self, context):
        # In batch mode, Test Render / single export act on the selected entry.
        entry = active_batch_entry(context)
        if entry is not None:
            return _build_entry(context, entry)
        return _build_one(context)

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
        entry = active_batch_entry(context)
        ss = context.scene.vgs_scenery if entry is None else entry.settings
        if not self.filepath:
            self.filepath = _parkobj_filename(ss.id)
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


class VGS_OT_export_batch(_SceneryModalBase):
    bl_idname = "vgs.export_batch"
    bl_label = "Export All"
    bl_description = (
        "Render every batch object and write one .parkobj per entry into a folder"
    )

    _status_verb = "Exporting batch"

    directory: StringProperty(subtype="DIR_PATH")
    filter_glob: StringProperty(default="", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _build(self, context):
        # Build every entry up front so all scene errors (empty collection,
        # missing tiles, duplicate ids, ...) surface before any rendering.
        bs = context.scene.vgs_batch
        if not bs.entries:
            raise scene_to_scenery.SceneError(
                "Batch list is empty. Add at least one object."
            )
        by_filename: dict[str, str] = {}
        for entry in bs.entries:
            if not entry.settings.id.strip():
                raise scene_to_scenery.SceneError(
                    f"Batch object '{entry.name}' has no Object ID."
                )
            filename = _parkobj_filename(entry.settings.id)
            if filename in by_filename:
                raise scene_to_scenery.SceneError(
                    f"Batch objects '{by_filename[filename]}' and '{entry.name}' "
                    f"both export as {filename}. Object IDs must be unique."
                )
            by_filename[filename] = entry.name
        payloads = []
        for entry in bs.entries:
            kind, obj = _build_entry(context, entry)
            payloads.append((kind, obj, _parkobj_filename(entry.settings.id)))
        return payloads

    def _prepare(self, context, payloads) -> None:
        super()._prepare(context, payloads)
        self._dir = bpy.path.abspath(self.directory)
        self._count = len(payloads)

    def _render(self, payloads) -> None:
        total = len(payloads)
        for i, (kind, obj, filename) in enumerate(payloads):
            ctx = make_context(self._lights, obj.units_per_tile, False)
            work = tempfile.mkdtemp(prefix="vgs_export_")
            _EXPORTERS[kind][0](obj, ctx, os.path.join(self._dir, filename), work)
            self.set_progress(i + 1, total)

    def _on_success(self, context):
        elapsed = int(time.monotonic() - self._start_time)
        build = f" (build {self._build_secs}s)" if self._build_secs else ""
        self.report(
            {"INFO"},
            f"Exported {self._count} .parkobj files to {self._dir} in {elapsed}s{build}",
        )
        return {"FINISHED"}


class VGS_OT_batch_add(Operator):
    bl_idname = "vgs.batch_add"
    bl_label = "Add Batch Object"
    bl_description = (
        "Add an object to the batch. Its settings start as a copy of the "
        "selected entry (or of the single-object settings for the first entry)"
    )

    def execute(self, context):
        bs = context.scene.vgs_batch
        had = len(bs.entries)
        entry = bs.entries.add()
        # Re-fetch the source after add(): growing a bpy collection can
        # invalidate references to existing items.
        if had:
            src = bs.entries[min(bs.index, had - 1)].settings
        else:
            src = context.scene.vgs_scenery
        _copy_props(src, entry.settings)
        entry.name = f"Object {len(bs.entries)}"
        bs.index = len(bs.entries) - 1
        return {"FINISHED"}


class VGS_OT_batch_remove(Operator):
    bl_idname = "vgs.batch_remove"
    bl_label = "Remove Batch Object"
    bl_description = "Remove the selected batch object"

    def execute(self, context):
        bs = context.scene.vgs_batch
        if not bs.entries:
            return {"CANCELLED"}
        bs.entries.remove(bs.index)
        bs.index = max(0, min(bs.index, len(bs.entries) - 1))
        return {"FINISHED"}


class VGS_OT_batch_offset_cursor(Operator):
    bl_idname = "vgs.batch_offset_cursor"
    bl_label = "Set from 3D Cursor"
    bl_description = (
        "Set the selected entry's collection offset to the 3D cursor position "
        "(place the cursor where the collection's origin was moved to)"
    )

    def execute(self, context):
        bs = context.scene.vgs_batch
        if not bs.entries:
            return {"CANCELLED"}
        bs.entries[bs.index].offset = context.scene.cursor.location
        return {"FINISHED"}


class VGS_OT_tile_add(Operator):
    bl_idname = "vgs.tile_add"
    bl_label = "Add Tile"
    bl_description = "Add a tile to the large-scenery footprint"

    def execute(self, context):
        ss = active_settings(context)
        ss.tiles.add()
        ss.tile_index = len(ss.tiles) - 1
        return {"FINISHED"}


class VGS_OT_tile_remove(Operator):
    bl_idname = "vgs.tile_remove"
    bl_label = "Remove Tile"
    bl_description = "Remove the selected tile"

    def execute(self, context):
        ss = active_settings(context)
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
        ss = active_settings(context)
        ss.entries.add()
        ss.entry_index = len(ss.entries) - 1
        return {"FINISHED"}


class VGS_OT_entry_remove(Operator):
    bl_idname = "vgs.entry_remove"
    bl_label = "Remove Entry"
    bl_description = "Remove the selected member object id"

    def execute(self, context):
        ss = active_settings(context)
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
    VGS_OT_export_batch,
    VGS_OT_batch_add,
    VGS_OT_batch_remove,
    VGS_OT_batch_offset_cursor,
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
