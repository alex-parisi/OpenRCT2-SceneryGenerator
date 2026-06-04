"""Blender operators for the scenery add-on: test render, threaded export,
and tile/light list management.

NOTE: no ``from __future__ import annotations`` — operators declare bpy
properties as annotations and PEP 563 would break registration.
"""

import os
import tempfile
import threading
import time
import traceback

import bpy
import numpy as np
from bpy.props import StringProperty
from bpy.types import Operator
from openrct2_scenery_generator.exporter import (
    export_large_scenery_test,
    export_large_scenery_to,
    export_small_scenery_test,
    export_small_scenery_to,
    export_wall_scenery_test,
    export_wall_scenery_to,
)
from openrct2_scenery_generator.loader import (
    build_large_scenery,
    build_small_scenery,
    build_wall_scenery,
)
from openrct2_x7_renderer.constants import LIGHT_DIFFUSE, LIGHT_SPECULAR, TILE_SIZE
from openrct2_x7_renderer.ray_trace import Context
from openrct2_x7_renderer.types import Light

from . import scene_to_scenery

_SPINNER_FRAMES = "|/-\\"
_LIGHT_TYPES = {"diffuse": LIGHT_DIFFUSE, "specular": LIGHT_SPECULAR}


def _normalize(v):
    arr = np.array(v, dtype=np.float64)
    n = np.linalg.norm(arr)
    return arr / n if n > 0 else arr


def _default_lights() -> list[Light]:
    return [
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, -1.0, 0.0]), 0.1),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, 0.5, -1.0]), 0.8),
        Light(LIGHT_SPECULAR, 1, _normalize([1.0, 1.65, -1.0]), 0.5),
        Light(LIGHT_DIFFUSE, 1, _normalize([1.0, 1.7, -1.0]), 0.8),
        Light(LIGHT_DIFFUSE, 0, np.array([0.0, 1.0, 0.0], dtype=np.float64), 0.45),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, 0.85, 1.0]), 0.475),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.75, 0.4, -1.0]), 0.6),
        Light(LIGHT_DIFFUSE, 0, _normalize([1.0, 0.25, 0.0]), 0.5),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, -0.5, 0.0]), 0.1),
    ]


def _lights_from_scene(context) -> list[Light]:
    ss = context.scene.vgs_scenery
    if not ss.lights:
        return _default_lights()
    return [
        Light(
            type=_LIGHT_TYPES[lt.type],
            shadow=int(lt.shadow),
            direction=_normalize(list(lt.direction)),
            intensity=lt.strength,
        )
        for lt in ss.lights
    ]


def _build_scenery_from_scene(context):
    """Main-thread step: read bpy data into a scenery object + its kind."""
    config, meshes, preview = scene_to_scenery.build_config_and_meshes(context)
    obj_type = config["object_type"]
    if obj_type == "scenery_large":
        return "large", build_large_scenery(config, meshes, preview)
    if obj_type == "scenery_wall":
        return "wall", build_wall_scenery(config, meshes, preview)
    return "small", build_small_scenery(config, meshes, preview)


class VGS_OT_test_render(Operator):
    bl_idname = "vgs.test_render"
    bl_label = "Test Render"
    bl_description = "Render the scenery quickly and show it in the Image Editor"

    def execute(self, context):
        try:
            kind, obj = _build_scenery_from_scene(context)
        except scene_to_scenery.SceneError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Invalid scenery: {e}")
            return {"CANCELLED"}

        ctx = Context.make(lights=_lights_from_scene(context), dither=True, upt=TILE_SIZE)
        tmp = tempfile.mkdtemp(prefix="vgs_test_")
        try:
            if kind == "large":
                export_large_scenery_test(obj, ctx, tmp)
                png = os.path.join(tmp, "preview_0.png")
            elif kind == "wall":
                export_wall_scenery_test(obj, ctx, tmp)
                png = os.path.join(tmp, "wall_0.png")
            else:
                export_small_scenery_test(obj, ctx, tmp)
                # Animated objects emit pose{g}_{d}.png; the static path emits
                # scenery_{i}.png. Preview whichever the first frame produced.
                png = os.path.join(tmp, "pose0_0.png" if obj.is_animated else "scenery_0.png")
        except Exception as e:
            self.report({"ERROR"}, f"Render failed: {e}")
            return {"CANCELLED"}

        if not os.path.exists(png):
            self.report({"WARNING"}, "Render produced no sprite")
            return {"CANCELLED"}

        img = bpy.data.images.load(png, check_existing=False)
        for area in context.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                break
        self.report({"INFO"}, f"Test sprite loaded: {img.name}")
        return {"FINISHED"}


class VGS_OT_export_parkobj(Operator):
    bl_idname = "vgs.export_parkobj"
    bl_label = "Export .parkobj"
    bl_description = "Render every sprite and write an OpenRCT2 scenery .parkobj"

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

    def execute(self, context):
        try:
            kind, obj = _build_scenery_from_scene(context)
        except scene_to_scenery.SceneError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Invalid scenery: {e}")
            return {"CANCELLED"}

        self._parkobj = bpy.path.abspath(self.filepath)
        self._work = tempfile.mkdtemp(prefix="vgs_export_")
        self._error = None
        self._done = False
        self._start_time = time.monotonic()
        self._spinner_step = 0
        lights = _lights_from_scene(context)

        def worker():
            try:
                ctx = Context.make(lights=lights, dither=True, upt=TILE_SIZE)
                if kind == "large":
                    export_large_scenery_to(obj, ctx, self._parkobj, self._work)
                elif kind == "wall":
                    export_wall_scenery_to(obj, ctx, self._parkobj, self._work)
                else:
                    export_small_scenery_to(obj, ctx, self._parkobj, self._work)
            except Exception:
                self._error = traceback.format_exc()
            finally:
                self._done = True

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        wm = context.window_manager
        wm.progress_begin(0, 1)
        context.window.cursor_modal_set("WAIT")
        self._set_status(context, _SPINNER_FRAMES[0], 0)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "TIMER":
            if self._done:
                return self._finish(context)
            self._spinner_step += 1
            glyph = _SPINNER_FRAMES[self._spinner_step % len(_SPINNER_FRAMES)]
            elapsed = int(time.monotonic() - self._start_time)
            self._set_status(context, glyph, elapsed)
        return {"PASS_THROUGH"}

    def _set_status(self, context, glyph: str, elapsed: int) -> None:
        context.workspace.status_text_set(f"{glyph} Exporting .parkobj... {elapsed}s")
        context.window_manager.progress_update((self._spinner_step % 20) / 20.0)

    def _finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        self._thread.join()
        if self._error:
            print(self._error)
            self.report({"ERROR"}, "Export failed; see the system console for details.")
            return {"CANCELLED"}
        elapsed = int(time.monotonic() - self._start_time)
        self.report({"INFO"}, f"Exported {os.path.basename(self._parkobj)} in {elapsed}s")
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
    VGS_OT_light_add,
    VGS_OT_light_remove,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
