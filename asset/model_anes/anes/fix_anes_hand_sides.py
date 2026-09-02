"""Correct the left/right handedness of every existing hand sprite.

The source hand artwork is right-handed. The current scene had that texture
unmirrored on the character's left and mirrored on the right. Flipping U once
on every existing hand quad corrects both sides without changing any authored
position, rotation, scale, rig binding, or pivot.
"""

from __future__ import annotations

from pathlib import Path

import bpy


BLEND_PATH = Path(r"C:\works\2.5D\asset\model_anes\anes\anes_2_5d.blend")
COLLECTION_NAME = "ANES_2_5D"


collection = bpy.data.collections.get(COLLECTION_NAME)
if collection is None:
    raise RuntimeError(f"Collection {COLLECTION_NAME!r} was not found")

flipped: list[str] = []
already_correct: list[str] = []
for obj in collection.all_objects:
    if obj.type != "MESH" or not obj.name.startswith(("hand_l", "hand_r")):
        continue
    handedness = "left" if obj.name.startswith("hand_l") else "right"
    if obj.get("handedness") == handedness:
        already_correct.append(obj.name)
        continue
    uv_layer = obj.data.uv_layers.active
    if uv_layer is None:
        raise RuntimeError(f"{obj.name!r} does not have an active UV layer")
    for loop_uv in uv_layer.data:
        loop_uv.uv.x = 1.0 - loop_uv.uv.x
    obj["handedness"] = handedness
    obj["source_hand"] = "right"
    flipped.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

result = {
    "blend_file": str(BLEND_PATH),
    "flipped": flipped,
    "already_correct": already_correct,
}
