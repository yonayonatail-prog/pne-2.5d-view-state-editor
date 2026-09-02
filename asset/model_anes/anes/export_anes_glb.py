"""Export the current ANES scene as a self-contained animated GLB."""

from __future__ import annotations

from pathlib import Path

import bpy


OUTPUT = Path(r"C:\works\2.5D\asset\model_anes\anes\anes_2_5d.glb")
COLLECTION_NAME = "ANES_2_5D"
VARIANT_BASES = {
    "face_variant_": "face_base",
    "hand_l_variant_": "hand_l",
    "hand_r_variant_": "hand_r",
}

collection = bpy.data.collections.get(COLLECTION_NAME)
if collection is None:
    raise RuntimeError(f"Collection {COLLECTION_NAME!r} was not found")

armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
if not armatures:
    raise RuntimeError("Expected at least one Armature, found none")
armature = armatures[0]


def sync_variant_transforms() -> list[str]:
    """Keep alternate sprites aligned with the manually adjusted base sprite.

    Variants share the same normalized pivot and parent as their base object,
    so copying the local transform preserves each texture's aspect ratio while
    applying the base object's authored position, rotation, and display scale.
    """
    synced: list[str] = []
    for obj in collection.all_objects:
        base_name = next(
            (name for prefix, name in VARIANT_BASES.items() if obj.name.startswith(prefix)),
            None,
        )
        if base_name is None:
            continue
        base = bpy.data.objects.get(base_name)
        if base is None:
            raise RuntimeError(f"Variant base {base_name!r} was not found")
        if obj.parent != base.parent:
            raise RuntimeError(
                f"{obj.name!r} and {base.name!r} must have the same parent before syncing"
            )
        obj.matrix_parent_inverse = base.matrix_parent_inverse.copy()
        obj.matrix_basis = base.matrix_basis.copy()
        synced.append(obj.name)
    bpy.context.view_layer.update()
    return synced


synced_variants = sync_variant_transforms()

export_objects = [
    obj for obj in collection.all_objects
    if obj.type in {"MESH", "EMPTY"}
]
export_objects.extend(armatures)

previous_selection = [obj for obj in bpy.context.selected_objects]
previous_active = bpy.context.view_layer.objects.active
visibility = {
    obj.name: (obj.hide_viewport, obj.hide_render, obj.hide_get())
    for obj in export_objects
}

try:
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in export_objects:
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.context.view_layer.update()

    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_nla_strips=False,
        export_skins=True,
        export_extras=True,
        export_yup=True,
        export_apply=False,
        export_image_format="AUTO",
        export_materials="EXPORT",
    )
finally:
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in export_objects:
        old_hide_viewport, old_hide_render, old_hide = visibility[obj.name]
        obj.hide_viewport = old_hide_viewport
        obj.hide_render = old_hide_render
        obj.hide_set(old_hide)
    for obj in previous_selection:
        if obj.name in bpy.context.view_layer.objects:
            obj.select_set(True)
    bpy.context.view_layer.objects.active = previous_active
    bpy.context.view_layer.update()

result = {
    "output": str(OUTPUT),
    "size": OUTPUT.stat().st_size,
    "objects": len(export_objects),
    "meshes": sum(obj.type == "MESH" for obj in export_objects),
    "armatures": [obj.name for obj in armatures],
    "actions": [action.name for action in bpy.data.actions],
    "synced_variants": synced_variants,
}
