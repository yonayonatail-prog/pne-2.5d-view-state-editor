"""PNE 2.5D View3D sidebar."""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


class PNE_UL_view_states(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        row = layout.row(align=True)
        row.prop(item, "view_id", text="", emboss=False, icon="RESTRICT_VIEW_OFF")
        row.prop(item, "yaw_deg", text="")


class PNE_PT_view_state_editor(Panel):
    bl_label = "PNE 2.5D"
    bl_idname = "PNE_PT_view_state_editor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PNE 2.5D"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.pne_settings

        box = layout.box()
        box.label(text="Character", icon="OUTLINER_OB_ARMATURE")
        box.prop(settings, "character_id", text="")
        box.prop(settings, "yaw_deg", slider=True)
        box.prop(settings, "pitch_deg", slider=True)
        row = box.row(align=True)
        row.prop(settings, "transition_mode", text="")
        row.prop(settings, "interpolation", text="")
        grid = box.grid_flow(columns=2, align=True)
        grid.label(text=f"State A: {settings.state_a or '-'}")
        grid.label(text=f"State B: {settings.state_b or '-'}")
        grid.label(text=f"Blend: {settings.blend:.3f}")
        grid.label(text=f"Mirror: {str(settings.mirror_active).lower()}")

        box = layout.box()
        box.label(text="Expression", icon="SHAPEKEY_DATA")
        box.prop(settings, "blink_l", slider=True)
        box.prop(settings, "blink_r", slider=True)
        box.prop(settings, "brow", slider=True)
        box.prop(settings, "mouth_open", slider=True)
        box.prop(settings, "smile", slider=True)
        box.prop(settings, "jaw", slider=True)

        box = layout.box()
        box.label(text="View States", icon="RENDERLAYERS")
        box.template_list("PNE_UL_view_states", "", settings, "views", settings, "active_view_index", rows=4)
        row = box.row(align=True)
        row.operator("pne.add_view", text="Add View", icon="ADD")
        row.operator("pne.duplicate_view", text="Duplicate", icon="DUPLICATE")
        row.operator("pne.remove_view", text="Remove", icon="REMOVE")
        if settings.views:
            index = min(settings.active_view_index, len(settings.views) - 1)
            state = settings.views[index]
            column = box.column(align=True)
            column.prop(state, "pitch_deg")
            column.prop(state, "flip_x")
            column.prop(state, "mirror_source")
            textures = box.column(align=True)
            textures.label(text="Texture Pack")
            textures.prop(state, "base_texture")
            textures.prop(state, "face_parts_texture")
            textures.prop(state, "occlusion_texture")
            textures.prop(state, "jaw_texture")

        box = layout.box()
        box.label(text="Texture Memory", icon="MEMORY")
        active_mb = sum(item.estimated_memory_mb for item in settings.views if item.view_id in settings.resident_active.split(","))
        prefetch_mb = sum(item.estimated_memory_mb for item in settings.views if item.view_id in settings.resident_prefetch.split(","))
        cache_mb = sum(item.estimated_memory_mb for item in settings.views if item.view_id in settings.resident_cache.split(","))
        grid = box.grid_flow(columns=2, align=True)
        grid.label(text="Active")
        grid.label(text=f"{active_mb:.1f} MB")
        grid.label(text="Prefetch")
        grid.label(text=f"{prefetch_mb:.1f} MB")
        grid.label(text="Cache")
        grid.label(text=f"{cache_mb:.1f} MB")
        grid.label(text="Estimated")
        grid.label(text=f"{active_mb + prefetch_mb + cache_mb:.1f} / {settings.max_gpu_memory_mb} MB")
        policy = box.row(align=True)
        policy.prop(settings, "active_views", text="A")
        policy.prop(settings, "prefetch_views", text="P")
        policy.prop(settings, "cache_views", text="C")
        box.prop(settings, "max_gpu_memory_mb")
        box.operator("pne.purge_cache", icon="TRASH")

        box = layout.box()
        box.label(text="Debug", icon="INFO")
        grid = box.grid_flow(columns=2, align=True)
        grid.prop(settings, "show_mesh", toggle=True)
        grid.prop(settings, "show_raw_alpha", toggle=True)
        grid.prop(settings, "show_render_order", toggle=True)
        grid.prop(settings, "preview_fifty", toggle=True)
        box.operator("pne.validate_character", icon="CHECKMARK")
        box.label(text=settings.validation_summary)
        for issue in list(settings.validation_issues)[:8]:
            icon = "ERROR" if issue.severity == "ERROR" else "WARNING_LARGE" if issue.severity == "WARNING" else "CHECKMARK"
            label = f"{issue.view_id}: {issue.message}" if issue.view_id else issue.message
            box.label(text=label, icon=icon)

        box = layout.box()
        box.label(text="Export", icon="EXPORT")
        box.prop(settings, "output_directory")
        resolutions = box.grid_flow(columns=2, align=True)
        resolutions.prop(settings, "base_resolution", text="Base")
        resolutions.prop(settings, "face_resolution", text="Face")
        resolutions.prop(settings, "occlusion_resolution", text="Occl.")
        resolutions.prop(settings, "jaw_resolution", text="Jaw")
        box.prop(settings, "ktx2_encoder")
        row = box.row(align=True)
        row.operator("pne.build_runtime_assets", icon="FILE_REFRESH")
        row.operator("pne.export_runtime_bundle", icon="EXPORT")

        box = layout.box()
        box.label(text="Sample", icon="EXPERIMENTAL")
        box.operator("pne.build_sample", icon="OUTLINER_OB_MESH")


class PNE_PT_trace_to_shape_key(Panel):
    bl_label = "Trace-to-ShapeKey"
    bl_idname = "PNE_PT_trace_to_shape_key"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PNE 2.5D"
    bl_parent_id = "PNE_PT_view_state_editor"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.pne_settings
        current_view = "-"
        if settings.views:
            index = min(settings.active_view_index, len(settings.views) - 1)
            current_view = settings.views[index].view_id

        box = layout.box()
        box.label(text=f"Current View: {current_view}", icon="RESTRICT_VIEW_OFF")
        box.prop(settings, "trace_role")
        box.prop(settings, "trace_side")
        box.prop(settings, "trace_basis_image")
        box.prop(settings, "trace_target_image")
        box.prop(settings, "trace_half_image")

        box = layout.box()
        box.label(text="Trace", icon="MOD_LINEART")
        box.prop(settings, "trace_mode")
        box.prop(settings, "trace_threshold", slider=True)
        row = box.row(align=True)
        row.prop(settings, "trace_min_area")
        row.prop(settings, "trace_smooth")
        row = box.row(align=True)
        row.prop(settings, "trace_stations")
        row.prop(settings, "trace_mesh_width")
        box.prop(settings, "trace_reverse_path")

        row = layout.row(align=True)
        row.operator("pne.trace_preview_paths", icon="HIDE_OFF")
        row.operator("pne.trace_clear_preview", text="Clear", icon="TRASH")
        layout.operator("pne.trace_build_pair", icon="SHAPEKEY_DATA")
        layout.prop(settings, "trace_blink_preview", slider=True)
        layout.operator("pne.trace_assign_current_view", icon="IMPORT")
        layout.label(text=settings.trace_status, icon="INFO")


UI_CLASSES = (PNE_UL_view_states, PNE_PT_view_state_editor, PNE_PT_trace_to_shape_key)
