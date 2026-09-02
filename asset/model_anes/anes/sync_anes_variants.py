"""Persist base face/hand transforms onto every alternate sprite.

Run this before exporting whenever the base face or either base hand has been
adjusted in Blender. The export script repeats the same sync defensively.
"""

from __future__ import annotations

from pathlib import Path

import bpy


BLEND_PATH = Path(r"C:\works\2.5D\asset\model_anes\anes\anes_2_5d.blend")
COLLECTION_NAME = "ANES_2_5D"
VARIANT_BASES = {
    "face_variant_": "face_base",
    "hand_l_variant_": "hand_l",
    "hand_r_variant_": "hand_r",
}


collection = bpy.data.collections.get(COLLECTION_NAME)
if collection is None:
    raise RuntimeError(f"Collection {COLLECTION_NAME!r} was not found")

synced = []
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
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

result = {
    "blend_file": str(BLEND_PATH),
    "synced_count": len(synced),
    "synced": synced,
}
