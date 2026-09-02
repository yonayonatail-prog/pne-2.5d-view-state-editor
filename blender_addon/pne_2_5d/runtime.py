"""Preview, expression synchronization, and debug state updates."""

from __future__ import annotations

import json
from typing import Iterable

import bpy

from .constants import DEBUG_TEXT_NAME
from .core import ViewPoint, compute_residency, resolve_view_blend, transition_weights
from .materials import iter_pne_materials, set_material_transition


_UPDATING = False


def view_objects(scene: bpy.types.Scene, view_id: str) -> list[bpy.types.Object]:
    settings = scene.pne_settings
    state = next((item for item in settings.views if item.view_id == view_id), None)
    if state is None:
        return []
    collection = bpy.data.collections.get(state.collection_name)
    return list(collection.all_objects) if collection else []


def all_pne_objects(scene: bpy.types.Scene) -> Iterable[bpy.types.Object]:
    for state in scene.pne_settings.views:
        yield from view_objects(scene, state.view_id)


def _set_shape_key(obj: bpy.types.Object, name: str, value: float) -> None:
    if not getattr(obj.data, "shape_keys", None):
        return
    block = obj.data.shape_keys.key_blocks.get(name)
    if block is not None:
        block.value = max(0.0, min(1.0, value))


def _set_blink(obj: bpy.types.Object, value: float) -> None:
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys is None:
        return
    keys = shape_keys.key_blocks
    half = keys.get("BlinkHalf")
    if half is None:
        _set_shape_key(obj, "Blink", value)
        return
    value = max(0.0, min(1.0, value))
    if value < 0.5:
        half.value = value * 2.0
        _set_shape_key(obj, "Blink", 0.0)
    else:
        half.value = (1.0 - value) * 2.0
        _set_shape_key(obj, "Blink", value * 2.0 - 1.0)


def apply_expressions(scene: bpy.types.Scene | None) -> None:
    if scene is None or not hasattr(scene, "pne_settings"):
        return
    settings = scene.pne_settings
    for obj in all_pne_objects(scene):
        role = str(obj.get("pne_role", ""))
        if role == "eye_l":
            _set_blink(obj, settings.blink_l)
        elif role == "eye_r":
            _set_blink(obj, settings.blink_r)
        elif role.startswith("brow_"):
            _set_shape_key(obj, "Up", max(0.0, settings.brow))
            _set_shape_key(obj, "Down", max(0.0, -settings.brow))
        elif role == "mouth":
            _set_shape_key(obj, "Open", settings.mouth_open)
            _set_shape_key(obj, "Smile", max(0.0, settings.smile))
            _set_shape_key(obj, "Frown", max(0.0, -settings.smile))
        elif role == "jaw":
            _set_shape_key(obj, "JawDown", settings.jaw)


def _debug_log(scene: bpy.types.Scene) -> None:
    settings = scene.pne_settings
    lines = [
        "PNE 2.5D DEBUG",
        f"Yaw        : {settings.yaw_deg:.3f}",
        f"Pitch      : {settings.pitch_deg:.3f}",
        f"View A     : {settings.state_a or '-'}",
        f"View B     : {settings.state_b or '-'}",
        f"Transition : {settings.transition_mode}",
        f"Blend      : {settings.blend:.3f}",
        f"Mirror     : {str(settings.mirror_active).lower()}",
        "Resident",
        *[f"  {item}" for item in settings.resident_active.split(",") if item],
        *[f"  {item} [prefetch]" for item in settings.resident_prefetch.split(",") if item],
        *[f"  {item} [cache]" for item in settings.resident_cache.split(",") if item],
    ]
    text = bpy.data.texts.get(DEBUG_TEXT_NAME) or bpy.data.texts.new(DEBUG_TEXT_NAME)
    text.clear()
    text.write("\n".join(lines) + "\n")
    scene["pne_debug"] = json.dumps(
        {
            "yaw": settings.yaw_deg,
            "pitch": settings.pitch_deg,
            "state_a": settings.state_a,
            "state_b": settings.state_b,
            "transition": settings.transition_mode,
            "blend": settings.blend,
            "resident": {
                "active": settings.resident_active.split(",") if settings.resident_active else [],
                "prefetch": settings.resident_prefetch.split(",") if settings.resident_prefetch else [],
                "cache": settings.resident_cache.split(",") if settings.resident_cache else [],
            },
        },
        ensure_ascii=False,
    )


def update_preview(scene: bpy.types.Scene | None) -> None:
    global _UPDATING
    if _UPDATING or scene is None or not hasattr(scene, "pne_settings"):
        return
    _UPDATING = True
    try:
        settings = scene.pne_settings
        points = [ViewPoint(item.view_id, item.yaw_deg, item.pitch_deg) for item in settings.views if item.view_id]
        result = resolve_view_blend(settings.yaw_deg, points, settings.interpolation)
        settings.state_a = result.state_a
        settings.state_b = result.state_b
        settings.raw_blend = result.raw_t
        settings.blend = 0.5 if settings.preview_fifty and result.state_a != result.state_b else result.blend

        state_lookup = {item.view_id: item for item in settings.views}
        active_ids = {item for item in (settings.state_a, settings.state_b) if item}
        settings.mirror_active = any(state_lookup[item].flip_x for item in active_ids if item in state_lookup)
        weights = transition_weights(settings.blend, settings.transition_mode)
        if settings.show_raw_alpha:
            material_mode = "ALPHA"
        else:
            material_mode = settings.transition_mode

        for state in settings.views:
            collection = bpy.data.collections.get(state.collection_name)
            if collection is None:
                continue
            is_active = state.view_id in active_ids
            collection.hide_viewport = not is_active
            collection.hide_render = not is_active
            if not is_active:
                continue
            slot = 0 if state.view_id == settings.state_a else 1
            if settings.state_a == settings.state_b:
                slot = 0
            opacity = weights[slot] if settings.state_a != settings.state_b else 1.0
            for obj in collection.all_objects:
                obj.show_wire = settings.show_mesh
                obj.show_all_edges = settings.show_mesh
                obj.show_name = settings.show_render_order
                obj.display_type = "WIRE" if settings.show_mesh else "TEXTURED"
                obj["pne_debug_render_order"] = int(obj.get("pne_render_order", 0)) if settings.show_render_order else -1
            for material in iter_pne_materials(collection.all_objects):
                set_material_transition(material, slot, settings.blend, material_mode, opacity)

        ordered = [item.id for item in sorted(points, key=lambda item: (item.yaw_deg, item.id))]
        old_cache = tuple(item for item in settings.resident_cache.split(",") if item)
        resident = compute_residency(
            ordered,
            settings.state_a,
            settings.state_b,
            old_cache,
            settings.prefetch_views,
            settings.cache_views,
        )
        settings.resident_active = ",".join(resident.active)
        settings.resident_prefetch = ",".join(resident.prefetch)
        settings.resident_cache = ",".join(resident.cache)
        apply_expressions(scene)
        _debug_log(scene)
    finally:
        _UPDATING = False


def purge_cache(scene: bpy.types.Scene) -> None:
    scene.pne_settings.resident_cache = ""
    update_preview(scene)
