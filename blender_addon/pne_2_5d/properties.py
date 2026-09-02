"""Persistent Blender RNA properties."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup


def _update_preview(self, context) -> None:
    from .runtime import update_preview

    update_preview(context.scene if context else bpy.context.scene)


def _update_expression(self, context) -> None:
    from .runtime import apply_expressions

    apply_expressions(context.scene if context else bpy.context.scene)


def _update_trace_preview(self, context) -> None:
    from .trace_shape_keys import set_trace_blink_value

    set_trace_blink_value(context.scene if context else bpy.context.scene, self.trace_blink_preview)


class PNE_ViewState(PropertyGroup):
    view_id: StringProperty(name="View ID", default="front_0")
    yaw_deg: FloatProperty(name="Yaw", default=0.0, min=-180.0, max=180.0, update=_update_preview)
    pitch_deg: FloatProperty(name="Pitch", default=0.0, min=-90.0, max=90.0)
    flip_x: BoolProperty(name="Flip X", default=False)
    mirror_source: StringProperty(name="Mirror Source", default="")
    collection_name: StringProperty(name="Collection", default="")
    base_texture: StringProperty(name="Base", subtype="FILE_PATH")
    face_parts_texture: StringProperty(name="Face Parts", subtype="FILE_PATH")
    occlusion_texture: StringProperty(name="Occlusion", subtype="FILE_PATH")
    jaw_texture: StringProperty(name="Jaw", subtype="FILE_PATH")
    estimated_memory_mb: FloatProperty(name="Estimated MB", default=0.0, min=0.0)


class PNE_ValidationIssue(PropertyGroup):
    severity: EnumProperty(
        name="Severity",
        items=(("ERROR", "Error", ""), ("WARNING", "Warning", ""), ("INFO", "Info", "")),
        default="INFO",
    )
    view_id: StringProperty(name="View")
    message: StringProperty(name="Message")


class PNE_Settings(PropertyGroup):
    character_id: StringProperty(name="Character", default="sample_character")
    yaw_deg: FloatProperty(name="Yaw", default=0.0, min=-180.0, max=180.0, update=_update_preview)
    pitch_deg: FloatProperty(name="Pitch", default=0.0, min=-90.0, max=90.0, update=_update_preview)
    transition_mode: EnumProperty(
        name="Transition",
        items=(
            ("STEP", "STEP", "Hard state switch"),
            ("SHARP", "SHARP", "Narrow debug crossfade"),
            ("DITHER", "DITHER", "Complementary pixel dither"),
            ("ALPHA", "ALPHA (Debug)", "Raw alpha debug crossfade"),
            ("WARP_DITHER", "WARP_DITHER (Future)", "Reserved; currently uses dither"),
        ),
        default="DITHER",
        update=_update_preview,
    )
    interpolation: EnumProperty(
        name="Interpolation",
        items=(("LINEAR", "Linear", ""), ("SMOOTHSTEP", "Smoothstep", ""), ("SHARP", "Sharp", "")),
        default="SMOOTHSTEP",
        update=_update_preview,
    )
    state_a: StringProperty(name="State A", default="")
    state_b: StringProperty(name="State B", default="")
    blend: FloatProperty(name="Blend", default=0.0, min=0.0, max=1.0)
    raw_blend: FloatProperty(name="Raw Blend", default=0.0, min=0.0, max=1.0)
    mirror_active: BoolProperty(name="Mirror", default=False)

    blink_l: FloatProperty(name="Blink L", default=0.0, min=0.0, max=1.0, update=_update_expression)
    blink_r: FloatProperty(name="Blink R", default=0.0, min=0.0, max=1.0, update=_update_expression)
    brow: FloatProperty(name="Brow", default=0.0, min=-1.0, max=1.0, update=_update_expression)
    mouth_open: FloatProperty(name="Mouth Open", default=0.0, min=0.0, max=1.0, update=_update_expression)
    smile: FloatProperty(name="Smile", default=0.0, min=-1.0, max=1.0, update=_update_expression)
    jaw: FloatProperty(name="Jaw", default=0.0, min=0.0, max=1.0, update=_update_expression)

    active_view_index: IntProperty(name="Active View", default=0, min=0)
    active_views: IntProperty(name="Active Views", default=2, min=1, max=8)
    prefetch_views: IntProperty(name="Prefetch Views", default=1, min=0, max=8, update=_update_preview)
    cache_views: IntProperty(name="Cache Views", default=2, min=0, max=16, update=_update_preview)
    max_gpu_memory_mb: IntProperty(name="GPU Budget", default=256, min=16, max=16384)
    resident_active: StringProperty(name="Resident Active", default="")
    resident_prefetch: StringProperty(name="Resident Prefetch", default="")
    resident_cache: StringProperty(name="Resident Cache", default="")

    show_mesh: BoolProperty(name="Show Mesh", default=False, update=_update_preview)
    show_raw_alpha: BoolProperty(name="Show Raw Alpha", default=False, update=_update_preview)
    show_render_order: BoolProperty(name="Show Render Order", default=False, update=_update_preview)
    preview_fifty: BoolProperty(name="50/50 Preview", default=False, update=_update_preview)

    output_directory: StringProperty(name="Output", subtype="DIR_PATH", default="//pne_export")
    base_resolution: IntProperty(name="Base Resolution", default=2048, min=32, max=8192)
    face_resolution: IntProperty(name="Face Resolution", default=1024, min=32, max=8192)
    occlusion_resolution: IntProperty(name="Occlusion Resolution", default=1024, min=32, max=8192)
    jaw_resolution: IntProperty(name="Jaw Resolution", default=512, min=32, max=8192)
    mipmap_base: BoolProperty(name="Base Mipmap", default=True)
    mipmap_face: BoolProperty(name="Face Mipmap", default=False)
    ktx2_encoder: StringProperty(name="toktx / basisu", subtype="FILE_PATH")
    validation_summary: StringProperty(name="Validation", default="Not validated")

    trace_basis_image: StringProperty(name="Basis / Open", subtype="FILE_PATH")
    trace_target_image: StringProperty(name="Target / Closed", subtype="FILE_PATH")
    trace_half_image: StringProperty(name="Half (Optional)", subtype="FILE_PATH")
    trace_role: EnumProperty(
        name="Role",
        items=(
            ("UPPER_EYELID", "Upper Eyelid", "Build an open ribbon with Blink Shape Keys"),
            ("BROW", "Brow", "Build a normalized brow ribbon"),
            ("MOUTH_LINE", "Mouth Line", "Build a normalized mouth-line ribbon"),
            ("NOSE", "Nose", "Build an optional nose-line ribbon"),
        ),
        default="UPPER_EYELID",
    )
    trace_side: EnumProperty(
        name="Side",
        items=(
            ("LEFT", "Left", "Character's left"),
            ("RIGHT", "Right", "Character's right"),
            ("CENTER", "Center", "Centered part such as mouth or nose"),
        ),
        default="LEFT",
    )
    trace_mode: EnumProperty(
        name="Trace Mode",
        items=(
            ("ALPHA", "Alpha", "Trace the image alpha channel"),
            ("THRESHOLD", "Threshold", "Trace dark pixels while respecting alpha"),
            ("EDGE", "Edge", "Trace alpha/luminance gradients"),
        ),
        default="ALPHA",
    )
    trace_threshold: FloatProperty(name="Threshold", default=0.45, min=0.001, max=0.999)
    trace_min_area: IntProperty(name="Min Area", default=24, min=1, max=1000000)
    trace_simplify: FloatProperty(name="Simplify", default=0.35, min=0.0, max=1.0)
    trace_smooth: FloatProperty(name="Smooth", default=0.20, min=0.0, max=1.0)
    trace_stations: IntProperty(name="Stations", default=32, min=4, max=256)
    trace_mesh_width: FloatProperty(name="Mesh Width", default=1.5, min=0.01, max=100.0)
    trace_reverse_path: BoolProperty(name="Reverse Direction", default=False)
    trace_blink_preview: FloatProperty(
        name="Blink Preview",
        default=0.0,
        min=0.0,
        max=1.0,
        update=_update_trace_preview,
    )
    trace_output_object: StringProperty(name="Trace Output")
    trace_status: StringProperty(name="Trace Status", default="Ready")

    views: CollectionProperty(type=PNE_ViewState)
    validation_issues: CollectionProperty(type=PNE_ValidationIssue)


PROPERTY_CLASSES = (PNE_ViewState, PNE_ValidationIssue, PNE_Settings)


def register_scene_properties() -> None:
    bpy.types.Scene.pne_settings = PointerProperty(type=PNE_Settings)


def unregister_scene_properties() -> None:
    del bpy.types.Scene.pne_settings
