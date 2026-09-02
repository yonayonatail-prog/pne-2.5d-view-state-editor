"""Pre-export validation for PNE characters."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import bpy

from .constants import REQUIRED_ROLES, REQUIRED_SHAPE_KEYS, ROLE_CONCEPT_Z, ROLE_RENDER_ORDER, TEXTURE_PACKS


@dataclass(frozen=True)
class ValidationResult:
    severity: str
    message: str
    view_id: str = ""


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _shape_key_names(obj: bpy.types.Object) -> set[str]:
    shape_keys = getattr(obj.data, "shape_keys", None)
    return set(shape_keys.key_blocks.keys()) if shape_keys else set()


def _required_shape_keys(obj: bpy.types.Object, role: str) -> set[str]:
    declared = obj.get("pne_required_shape_keys")
    if declared is not None:
        return {item.strip() for item in str(declared).split(",") if item.strip()}
    return set(REQUIRED_SHAPE_KEYS.get(role, ()))


def _texture_items(state) -> tuple[tuple[str, str], ...]:
    return (
        ("base", state.base_texture),
        ("face_parts", state.face_parts_texture),
        ("occlusion", state.occlusion_texture),
        ("jaw", state.jaw_texture),
    )


def validate_character(scene: bpy.types.Scene, *, update_ui: bool = True) -> list[ValidationResult]:
    settings = scene.pne_settings
    results: list[ValidationResult] = []

    if not settings.character_id.strip():
        results.append(ValidationResult("ERROR", "Character ID is empty"))
    if not settings.views:
        results.append(ValidationResult("ERROR", "No View States are registered"))

    seen_view_ids: set[str] = set()
    seen_yaw: dict[float, str] = {}
    seen_pne_ids: dict[str, str] = {}
    view_ids = {state.view_id for state in settings.views if state.view_id}

    for state in settings.views:
        view_id = state.view_id.strip()
        if not view_id:
            results.append(ValidationResult("ERROR", "View ID is empty"))
            continue
        if view_id in seen_view_ids:
            results.append(ValidationResult("ERROR", f"Duplicate View ID: {view_id}", view_id))
        seen_view_ids.add(view_id)
        yaw_key = round(float(state.yaw_deg), 4)
        if yaw_key in seen_yaw:
            results.append(ValidationResult("ERROR", f"Duplicate Yaw: {state.yaw_deg:g}° (also {seen_yaw[yaw_key]})", view_id))
        else:
            seen_yaw[yaw_key] = view_id

        if state.mirror_source and state.mirror_source not in view_ids:
            results.append(ValidationResult("ERROR", f"Mirror Source does not exist: {state.mirror_source}", view_id))

        collection = bpy.data.collections.get(state.collection_name)
        if collection is None:
            results.append(ValidationResult("ERROR", f"Collection does not exist: {state.collection_name or '(empty)'}", view_id))
            continue

        role_objects: dict[str, list[bpy.types.Object]] = {}
        for obj in collection.all_objects:
            missing = [key for key in ("pne_id", "pne_role", "pne_view_id") if key not in obj]
            if missing:
                results.append(ValidationResult("ERROR", f"{obj.name}: missing custom properties {', '.join(missing)}", view_id))
                continue
            pne_id = str(obj["pne_id"])
            role = str(obj["pne_role"])
            if pne_id in seen_pne_ids:
                results.append(ValidationResult("ERROR", f"Duplicate pne_id: {pne_id} (also {seen_pne_ids[pne_id]})", view_id))
            else:
                seen_pne_ids[pne_id] = obj.name
            if str(obj["pne_view_id"]) != view_id:
                results.append(ValidationResult("ERROR", f"{obj.name}: pne_view_id does not match the state", view_id))
            role_objects.setdefault(role, []).append(obj)

            if "pne_render_order" not in obj:
                results.append(ValidationResult("ERROR", f"{obj.name}: renderOrder is missing", view_id))
            elif role in ROLE_RENDER_ORDER and int(obj["pne_render_order"]) != ROLE_RENDER_ORDER[role]:
                results.append(
                    ValidationResult("WARNING", f"{obj.name}: renderOrder {obj['pne_render_order']} should be {ROLE_RENDER_ORDER[role]}", view_id)
                )
            if "pne_concept_z" not in obj:
                results.append(ValidationResult("ERROR", f"{obj.name}: physical/concept Z is missing", view_id))
            elif role in ROLE_CONCEPT_Z and not math.isclose(float(obj["pne_concept_z"]), ROLE_CONCEPT_Z[role], abs_tol=0.0001):
                results.append(ValidationResult("WARNING", f"{obj.name}: concept Z differs from role default", view_id))

            padding = int(obj.get("pne_uv_padding", 0))
            if padding < 32:
                results.append(ValidationResult("WARNING", f"{obj.name}: UV safety margin {padding}px < 32px", view_id))

            if obj.get("pne_trace_output"):
                if obj.type != "MESH":
                    results.append(ValidationResult("ERROR", f"{obj.name}: Trace output is not a Mesh", view_id))
                else:
                    stations = int(obj.get("pne_trace_stations", 0))
                    if stations < 4:
                        results.append(ValidationResult("ERROR", f"{obj.name}: invalid trace station count", view_id))
                    if len(obj.data.vertices) != stations * 2:
                        results.append(ValidationResult("ERROR", f"{obj.name}: trace vertex count does not match stations", view_id))
                    if len(obj.data.polygons) != max(0, stations - 1):
                        results.append(ValidationResult("ERROR", f"{obj.name}: trace face count does not match stations", view_id))
                    if obj.name != obj.data.name:
                        results.append(ValidationResult("ERROR", f"{obj.name}: Mesh datablock name must match Object name", view_id))
                for key in ("pne_subrole", "pne_expression_channel", "pne_template_id", "pne_topology_hash"):
                    if not str(obj.get(key, "")).strip():
                        results.append(ValidationResult("ERROR", f"{obj.name}: missing {key}", view_id))

        missing_roles = sorted(REQUIRED_ROLES.difference(role_objects))
        for role in missing_roles:
            results.append(ValidationResult("ERROR", f"Missing role: {role.upper()}", view_id))
        for role, objects in role_objects.items():
            for obj in objects:
                required_keys = _required_shape_keys(obj, role)
                missing_keys = sorted(required_keys.difference(_shape_key_names(obj)))
                if missing_keys:
                    results.append(ValidationResult("ERROR", f"{obj.name}: missing Shape Key(s) {', '.join(missing_keys)}", view_id))

        for pack, raw_path in _texture_items(state):
            if pack not in TEXTURE_PACKS:
                continue
            path = Path(bpy.path.abspath(raw_path)) if raw_path else None
            if path is None or not path.is_file():
                results.append(ValidationResult("ERROR", f"Texture does not exist: {pack} ({raw_path or 'empty'})", view_id))
                continue
            try:
                image = bpy.data.images.load(str(path), check_existing=True)
                width, height = int(image.size[0]), int(image.size[1])
                if width <= 0 or height <= 0:
                    results.append(ValidationResult("ERROR", f"Texture has invalid resolution: {pack}", view_id))
                elif not _is_power_of_two(width) or not _is_power_of_two(height):
                    results.append(ValidationResult("WARNING", f"Texture is not power-of-two: {pack} ({width}x{height})", view_id))
            except RuntimeError as exc:
                results.append(ValidationResult("ERROR", f"Texture cannot be loaded: {pack} ({exc})", view_id))

        if not any(item.severity == "ERROR" and item.view_id == view_id for item in results):
            results.append(ValidationResult("INFO", "View State is valid", view_id))

    if update_ui:
        settings.validation_issues.clear()
        for result in results:
            issue = settings.validation_issues.add()
            issue.severity = result.severity
            issue.view_id = result.view_id
            issue.message = result.message
        errors = sum(item.severity == "ERROR" for item in results)
        warnings = sum(item.severity == "WARNING" for item in results)
        settings.validation_summary = f"{errors} error(s), {warnings} warning(s)"
    return results
