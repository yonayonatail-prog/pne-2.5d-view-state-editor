"""Bind ANES billboard planes to the current rig with rigid 1.0 weights."""

from __future__ import annotations

import bpy


armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
if len(armatures) != 1:
    raise RuntimeError(f"Expected exactly one Armature, found {len(armatures)}")
armature = armatures[0]

collection = bpy.data.collections.get("ANES_2_5D")
if collection is None:
    raise RuntimeError("ANES_2_5D collection was not found")

# The manually arranged screen-right upper-arm image originates from the
# source file named *_l. Bind by its actual position, not its source label.
explicit_mapping = {
    "hair_back": "head",
    "face_base": "head",
    "hair_side": "head",
    "hair_front": "head",
    "headphone": "head",
    "headphone_spindles": "head",
    "torso_upper": "torso",
    "torso_lower": "pelvis",
    "upper_arm_l": "upper_arm_r",
    "forearm_r": "forearm_r",
    "hand_r": "forearm_r",
    "upper_arm_r": "upper_arm_l",
    "forearm_l": "forearm_l",
    "hand_l": "forearm_l",
    "leg_r": "thigh_r",
    "foot_r": "shin_r",
    "leg_l": "thigh_l",
    "foot_l": "shin_l",
}


def target_bone_for(obj: bpy.types.Object) -> str | None:
    if obj.name.startswith("face_variant_"):
        return "head"
    if obj.name.startswith("hand_l_variant_"):
        return "forearm_l"
    if obj.name.startswith("hand_r_variant_"):
        return "forearm_r"
    return explicit_mapping.get(obj.name)


bone_names = {bone.name for bone in armature.data.bones}
bound: list[dict[str, object]] = []
unmapped: list[str] = []

for obj in collection.all_objects:
    if obj.type != "MESH":
        continue
    target_bone = target_bone_for(obj)
    if target_bone is None:
        unmapped.append(obj.name)
        continue
    if target_bone not in bone_names:
        raise RuntimeError(f"Bone {target_bone!r} required by {obj.name!r} was not found")

    # This rig stage uses exactly one deform group per billboard.
    obj.vertex_groups.clear()
    group = obj.vertex_groups.new(name=target_bone)
    vertex_indices = list(range(len(obj.data.vertices)))
    group.add(vertex_indices, 1.0, "REPLACE")

    modifier = obj.modifiers.get("ANES_RigidSkin")
    if modifier is None:
        modifier = obj.modifiers.new(name="ANES_RigidSkin", type="ARMATURE")
    modifier.object = armature
    modifier.use_vertex_groups = True
    modifier.use_bone_envelopes = False
    modifier.use_deform_preserve_volume = False

    obj["rigid_weight_bone"] = target_bone
    obj["rigid_weight"] = 1.0
    bound.append(
        {
            "object": obj.name,
            "bone": target_bone,
            "vertices": len(vertex_indices),
        }
    )

if unmapped:
    raise RuntimeError(f"Unmapped mesh objects: {sorted(unmapped)}")

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

result = {
    "filepath": bpy.data.filepath,
    "armature": armature.name,
    "bound_count": len(bound),
    "bound": bound,
    "unmapped": unmapped,
}
