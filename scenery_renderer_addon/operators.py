"""
Blender operators for the scenery add-on: test render, threaded export,
and tile/light list management.
"""

import os
import shutil
import tempfile

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from openrct2_object_common.blender.collection_ops import make_collection_ops
from openrct2_object_common.blender.lights_ui import make_light_ops
from openrct2_object_common.blender.modal import (
    ExportParkobjModalBase,
    RenderModalBase,
    TestRenderModalBase,
)
from openrct2_object_common.blender.props import copy_props
from openrct2_object_common.blender.registration import register_classes, unregister_classes
from openrct2_object_common.parkobj import parkobj_filename
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
        raise scene_to_scenery.SceneError(f"Batch object '{label}': no Collection assigned.")
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
        self._read_render_settings(context.scene.vgs_scenery)


class VGS_OT_test_render(TestRenderModalBase, _SceneryModalBase):
    bl_idname = "vgs.test_render"
    bl_label = "Test Render"
    bl_description = "Render the scenery quickly and show it in the Image Editor"

    _tmp_prefix = "vgs_test_"

    def _render(self, payload) -> None:
        kind, obj = payload
        # Render at the real in-game scale
        ctx = self._make_context(obj.units_per_tile)
        _EXPORTERS[kind][1](obj, ctx, self._tmp)
        # Every kind writes a combined contact sheet
        self._png = os.path.join(self._tmp, "preview_combined.png")


class VGS_OT_export_parkobj(ExportParkobjModalBase, _SceneryModalBase):
    bl_idname = "vgs.export_parkobj"
    bl_label = "Export .parkobj"
    bl_description = "Render every sprite and write an OpenRCT2 scenery .parkobj"

    _tmp_prefix = "vgs_export_"

    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext = ".parkobj"
    filter_glob: StringProperty(default="*.parkobj", options={"HIDDEN"})

    def _default_filename(self, context) -> str:
        # In batch mode the single export acts on the selected entry's settings.
        return parkobj_filename(active_settings(context).id, default="scenery")

    def _render(self, payload) -> None:
        kind, obj = payload
        ctx = self._make_context(obj.units_per_tile)
        _EXPORTERS[kind][0](obj, ctx, self._parkobj, self._work, progress=self.set_progress)


class VGS_OT_export_batch(_SceneryModalBase):
    bl_idname = "vgs.export_batch"
    bl_label = "Export All"
    bl_description = "Render every batch object and write one .parkobj per entry into a folder"

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
            raise scene_to_scenery.SceneError("Batch list is empty. Add at least one object.")
        by_filename: dict[str, str] = {}
        for entry in bs.entries:
            if not entry.settings.id.strip():
                raise scene_to_scenery.SceneError(f"Batch object '{entry.name}' has no Object ID.")
            filename = parkobj_filename(entry.settings.id, default="scenery")
            if filename in by_filename:
                raise scene_to_scenery.SceneError(
                    f"Batch objects '{by_filename[filename]}' and '{entry.name}' "
                    f"both export as {filename}. Object IDs must be unique."
                )
            by_filename[filename] = entry.name
        payloads = []
        for entry in bs.entries:
            kind, obj = _build_entry(context, entry)
            payloads.append((kind, obj, parkobj_filename(entry.settings.id, default="scenery")))
        return payloads

    def _prepare(self, context, payloads) -> None:
        super()._prepare(context, payloads)
        self._dir = bpy.path.abspath(self.directory)
        self._count = len(payloads)

    def _render(self, payloads) -> None:
        total = len(payloads)
        for i, (kind, obj, filename) in enumerate(payloads):
            ctx = self._make_context(obj.units_per_tile)
            work = tempfile.mkdtemp(prefix="vgs_export_")
            try:
                _EXPORTERS[kind][0](obj, ctx, os.path.join(self._dir, filename), work)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            self.set_progress(i + 1, total)

    def _on_success(self, context):
        self.report(
            {"INFO"},
            f"Exported {self._count} .parkobj files to {self._dir} in {self._elapsed_suffix()}",
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
        copy_props(src, entry.settings)
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


# Tiles and group entries are edited on the active settings (the selected batch
# entry's, or the scene's), so these resolve through active_settings rather than
# a fixed scene attribute.
VGS_OT_tile_add, VGS_OT_tile_remove = make_collection_ops(
    prefix="vgs",
    name="tile",
    get_settings=active_settings,
    coll_attr="tiles",
    index_attr="tile_index",
    add_label="Add Tile",
    add_description="Add a tile to the large-scenery footprint",
    remove_label="Remove Tile",
    remove_description="Remove the selected tile",
)

VGS_OT_entry_add, VGS_OT_entry_remove = make_collection_ops(
    prefix="vgs",
    name="entry",
    get_settings=active_settings,
    coll_attr="entries",
    index_attr="entry_index",
    add_label="Add Entry",
    add_description="Add a member object id to the scenery group",
    remove_label="Remove Entry",
    remove_description="Remove the selected member object id",
)

VGS_OT_light_add, VGS_OT_light_remove = make_light_ops(prefix="vgs", settings_attr="vgs_scenery")


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
    register_classes(_CLASSES)


def unregister():
    unregister_classes(_CLASSES)
