"""User-facing Blender operators."""

from __future__ import annotations

import re

import bpy
from bpy.types import Operator

from .constants import MASTER_COLLECTION


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
    return cleaned or "view"


def _unique_view_id(settings, base: str) -> str:
    used = {item.view_id for item in settings.views}
    candidate = _safe_id(base)
    if candidate not in used:
        return candidate
    index = 2
    while f"{candidate}_{index}" in used:
        index += 1
    return f"{candidate}_{index}"


class PNE_OT_build_sample(Operator):
    bl_idname = "pne.build_sample"
    bl_label = "Build Sample Character"
    bl_description = "Create the fixed four-direction PNE sample with meshes, Shape Keys, textures, and runtime IDs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .sample import build_sample

        try:
            count, source_root = build_sample(context.scene)
        except Exception as exc:
            self.report({"ERROR"}, f"Sample build failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Built {count} View States; source textures: {source_root}")
        return {"FINISHED"}


class PNE_OT_add_view(Operator):
    bl_idname = "pne.add_view"
    bl_label = "Add View"
    bl_description = "Add an empty View State collection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.pne_settings
        master = bpy.data.collections.get(MASTER_COLLECTION)
        if master is None:
            master = bpy.data.collections.new(MASTER_COLLECTION)
            context.scene.collection.children.link(master)
        next_yaw = max((item.yaw_deg for item in settings.views), default=-30.0) + 30.0
        view_id = _unique_view_id(settings, f"view_{round(next_yaw):g}")
        collection = bpy.data.collections.new(f"STATE_{view_id}")
        master.children.link(collection)
        state = settings.views.add()
        state.view_id = view_id
        state.yaw_deg = next_yaw
        state.collection_name = collection.name
        settings.active_view_index = len(settings.views) - 1
        from .runtime import update_preview

        update_preview(context.scene)
        return {"FINISHED"}


class PNE_OT_duplicate_view(Operator):
    bl_idname = "pne.duplicate_view"
    bl_label = "Duplicate"
    bl_description = "Duplicate the selected View State as an independent collection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.pne_settings.views)

    def execute(self, context):
        settings = context.scene.pne_settings
        index = min(settings.active_view_index, len(settings.views) - 1)
        source_state = settings.views[index]
        source_collection = bpy.data.collections.get(source_state.collection_name)
        if source_collection is None:
            self.report({"ERROR"}, "Source View collection does not exist")
            return {"CANCELLED"}
        master = bpy.data.collections.get(MASTER_COLLECTION)
        if master is None:
            self.report({"ERROR"}, "PNE master collection does not exist")
            return {"CANCELLED"}
        view_id = _unique_view_id(settings, f"{source_state.view_id}_copy")
        collection = bpy.data.collections.new(f"STATE_{view_id}")
        master.children.link(collection)
        for source in source_collection.objects:
            duplicate = source.copy()
            if source.data:
                duplicate.data = source.data.copy()
            collection.objects.link(duplicate)
            role = str(source.get("pne_role", ""))
            duplicate["pne_id"] = f"{role}.{view_id}"
            duplicate["pne_view_id"] = view_id
            for slot in duplicate.material_slots:
                if slot.material and slot.material.get("pne_material"):
                    slot.material = slot.material.copy()
        state = settings.views.add()
        state.view_id = view_id
        state.yaw_deg = min(180.0, source_state.yaw_deg + 30.0)
        state.pitch_deg = source_state.pitch_deg
        state.flip_x = source_state.flip_x
        state.mirror_source = source_state.mirror_source
        state.collection_name = collection.name
        state.base_texture = source_state.base_texture
        state.face_parts_texture = source_state.face_parts_texture
        state.occlusion_texture = source_state.occlusion_texture
        state.jaw_texture = source_state.jaw_texture
        settings.active_view_index = len(settings.views) - 1
        from .runtime import update_preview

        update_preview(context.scene)
        return {"FINISHED"}


class PNE_OT_remove_view(Operator):
    bl_idname = "pne.remove_view"
    bl_label = "Remove"
    bl_description = "Remove the selected View State and its generated objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.pne_settings.views)

    def execute(self, context):
        settings = context.scene.pne_settings
        index = min(settings.active_view_index, len(settings.views) - 1)
        state = settings.views[index]
        collection = bpy.data.collections.get(state.collection_name)
        if collection:
            for obj in list(collection.all_objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(collection)
        settings.views.remove(index)
        settings.active_view_index = max(0, min(index, len(settings.views) - 1))
        from .runtime import update_preview

        update_preview(context.scene)
        return {"FINISHED"}


class PNE_OT_validate(Operator):
    bl_idname = "pne.validate_character"
    bl_label = "Validate Character"
    bl_description = "Validate View IDs, roles, Shape Keys, textures, runtime properties, padding, and mirrors"

    def execute(self, context):
        from .validator import validate_character

        results = validate_character(context.scene)
        errors = sum(item.severity == "ERROR" for item in results)
        warnings = sum(item.severity == "WARNING" for item in results)
        level = {"ERROR"} if errors else {"WARNING"} if warnings else {"INFO"}
        self.report(level, f"Validation: {errors} error(s), {warnings} warning(s)")
        return {"FINISHED"}


class PNE_OT_build_runtime(Operator):
    bl_idname = "pne.build_runtime_assets"
    bl_label = "Build Runtime Assets"
    bl_description = "Resize source packs and build PNG preview plus KTX2 runtime textures"

    def execute(self, context):
        from .exporter import build_runtime_assets
        from .validator import validate_character

        errors = [item for item in validate_character(context.scene) if item.severity == "ERROR"]
        if errors:
            self.report({"ERROR"}, f"Build blocked by {len(errors)} validation error(s)")
            return {"CANCELLED"}
        try:
            root, manifest = build_runtime_assets(context.scene)
        except Exception as exc:
            self.report({"ERROR"}, f"Runtime build failed: {exc}")
            return {"CANCELLED"}
        encoders = ", ".join(manifest.get("encoders", {}).keys())
        self.report({"INFO"}, f"Runtime textures built at {root} ({encoders})")
        return {"FINISHED"}


class PNE_OT_export_bundle(Operator):
    bl_idname = "pne.export_runtime_bundle"
    bl_label = "Export Runtime Bundle"
    bl_description = "Validate and export character.glb, character.states.json, and per-view textures"

    def execute(self, context):
        from .exporter import export_runtime_bundle

        try:
            root, glb_path, json_path = export_runtime_bundle(context.scene)
        except Exception as exc:
            self.report({"ERROR"}, f"Export failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {glb_path.name} + {json_path.name} to {root}")
        return {"FINISHED"}


class PNE_OT_purge_cache(Operator):
    bl_idname = "pne.purge_cache"
    bl_label = "Purge Cache"
    bl_description = "Clear the logical texture LRU cache while retaining active and prefetched views"

    def execute(self, context):
        from .runtime import purge_cache

        purge_cache(context.scene)
        self.report({"INFO"}, "Logical texture cache purged")
        return {"FINISHED"}


class PNE_OT_trace_preview_paths(Operator):
    bl_idname = "pne.trace_preview_paths"
    bl_label = "Preview Paths"
    bl_description = "Trace Basis and Target images and show their normalized guide paths"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .trace_shape_keys import TraceError, append_trace_error, build_trace_data, create_path_preview

        settings = context.scene.pne_settings
        try:
            data = build_trace_data(settings)
            objects = create_path_preview(context.scene, data)
        except (TraceError, RuntimeError, ValueError) as exc:
            settings.trace_status = f"Error: {exc}"
            append_trace_error(settings, "preview_paths", exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.trace_status = f"Preview: {len(data.basis_centers)} stations"
        for obj in context.selected_objects:
            obj.select_set(False)
        if objects:
            objects[0].select_set(True)
            context.view_layer.objects.active = objects[0]
        self.report({"INFO"}, settings.trace_status)
        return {"FINISHED"}


class PNE_OT_trace_build_pair(Operator):
    bl_idname = "pne.trace_build_pair"
    bl_label = "Build ShapeKey Pair"
    bl_description = "Build one normalized ribbon mesh with Basis and Blink Shape Keys"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .trace_shape_keys import (
            TraceError,
            append_trace_error,
            append_trace_log,
            build_trace_data,
            create_shape_key_mesh,
            trace_log_payload,
        )

        settings = context.scene.pne_settings
        try:
            data = build_trace_data(settings)
            obj = create_shape_key_mesh(context.scene, settings, data)
            append_trace_log(trace_log_payload(settings, data, status="OK", object_name=obj.name))
        except (TraceError, RuntimeError, ValueError) as exc:
            settings.trace_status = f"Error: {exc}"
            append_trace_error(settings, "build_shape_key_pair", exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        settings.trace_status = f"Built {len(data.basis_vertices)} verts / {len(data.faces)} faces"
        self.report({"INFO"}, settings.trace_status)
        return {"FINISHED"}


class PNE_OT_trace_assign_current_view(Operator):
    bl_idname = "pne.trace_assign_current_view"
    bl_label = "Assign To Current View"
    bl_description = "Move the generated trace mesh into the selected PNE View State"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .trace_shape_keys import TraceError, append_trace_error, assign_to_current_view

        settings = context.scene.pne_settings
        obj = context.active_object
        if obj is None or not obj.get("pne_trace_output"):
            obj = bpy.data.objects.get(settings.trace_output_object)
        if obj is None or not obj.get("pne_trace_output"):
            self.report({"ERROR"}, "Build or select a Trace-to-ShapeKey output first")
            return {"CANCELLED"}
        try:
            view_id, pne_id = assign_to_current_view(context.scene, settings, obj)
        except (TraceError, RuntimeError, ValueError) as exc:
            settings.trace_status = f"Error: {exc}"
            append_trace_error(settings, "assign_current_view", exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.trace_status = f"Assigned {pne_id} to {view_id}"
        self.report({"INFO"}, settings.trace_status)
        return {"FINISHED"}


class PNE_OT_trace_clear_preview(Operator):
    bl_idname = "pne.trace_clear_preview"
    bl_label = "Clear Trace Preview"
    bl_description = "Remove only generated Trace-to-ShapeKey preview objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .trace_shape_keys import clear_trace_preview

        clear_trace_preview(context.scene)
        context.scene.pne_settings.trace_output_object = ""
        context.scene.pne_settings.trace_status = "Ready"
        self.report({"INFO"}, "Trace preview cleared")
        return {"FINISHED"}


OPERATOR_CLASSES = (
    PNE_OT_build_sample,
    PNE_OT_add_view,
    PNE_OT_duplicate_view,
    PNE_OT_remove_view,
    PNE_OT_validate,
    PNE_OT_build_runtime,
    PNE_OT_export_bundle,
    PNE_OT_purge_cache,
    PNE_OT_trace_preview_paths,
    PNE_OT_trace_build_pair,
    PNE_OT_trace_assign_current_view,
    PNE_OT_trace_clear_preview,
)
