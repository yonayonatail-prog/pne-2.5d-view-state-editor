"""Create a subtle looping idle Action without overwriting user animation."""

from __future__ import annotations

import math

import bpy
from mathutils import Quaternion


ACTION_NAME = "ANES_Idle_Loop"
START_FRAME = 1
END_FRAME = 49


armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
if len(armatures) != 1:
    raise RuntimeError(f"Expected exactly one Armature, found {len(armatures)}")
armature = armatures[0]
animation_data = armature.animation_data_create()
previous_action = animation_data.action

old_generated = bpy.data.actions.get(ACTION_NAME)
if old_generated is not None:
    if animation_data.action == old_generated:
        animation_data.action = None
    bpy.data.actions.remove(old_generated)

action = bpy.data.actions.new(ACTION_NAME)
action["motion_id"] = "idle"
action["loop_start"] = START_FRAME
action["loop_end"] = END_FRAME
action["description"] = "Subtle breathing, head bob, body sway, and delayed arm motion"
animation_data.action = action

required_bones = {
    "head",
    "torso",
    "pelvis",
    "upper_arm_l",
    "forearm_l",
    "upper_arm_r",
    "forearm_r",
}
missing = sorted(required_bones - set(armature.pose.bones.keys()))
if missing:
    raise RuntimeError(f"Required bones are missing: {missing}")

# Start the generated action from the exact rest pose. This does not modify
# the keyframes stored in the user's previous Action.
for pose_bone in armature.pose.bones:
    pose_bone.location = (0.0, 0.0, 0.0)
    pose_bone.rotation_mode = "QUATERNION"
    pose_bone.rotation_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    pose_bone.scale = (1.0, 1.0, 1.0)


def set_rotation_z(bone_name: str, frame: int, degrees: float) -> None:
    pose_bone = armature.pose.bones[bone_name]
    pose_bone.rotation_quaternion = Quaternion(
        (0.0, 0.0, 1.0), math.radians(degrees)
    )
    pose_bone.keyframe_insert(
        data_path="rotation_quaternion",
        frame=frame,
        group=bone_name,
    )


def set_location_y(bone_name: str, frame: int, value: float) -> None:
    pose_bone = armature.pose.bones[bone_name]
    pose_bone.location = (0.0, value, 0.0)
    pose_bone.keyframe_insert(data_path="location", frame=frame, group=bone_name)


def set_scale_xy(bone_name: str, frame: int, scale_x: float, scale_y: float) -> None:
    pose_bone = armature.pose.bones[bone_name]
    pose_bone.scale = (scale_x, scale_y, 1.0)
    pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)


# Five matching loop poses. The middle poses approximate a soft sine wave.
frames = (1, 13, 25, 37, 49)
head_rotations = (0.0, 1.2, 0.0, -1.0, 0.0)
head_bobs = (0.0, 0.010, 0.0, -0.006, 0.0)
torso_rotations = (0.0, -0.55, 0.0, 0.45, 0.0)
pelvis_rotations = (0.0, 0.22, 0.0, -0.18, 0.0)
torso_scale_x = (1.0, 1.007, 1.0, 1.004, 1.0)
torso_scale_y = (1.0, 1.014, 1.0, 1.008, 1.0)

for index, frame in enumerate(frames):
    set_rotation_z("head", frame, head_rotations[index])
    set_location_y("head", frame, head_bobs[index])
    set_rotation_z("torso", frame, torso_rotations[index])
    set_scale_xy("torso", frame, torso_scale_x[index], torso_scale_y[index])
    set_rotation_z("pelvis", frame, pelvis_rotations[index])

# Arms lag behind the torso and move in opposite directions, which avoids a
# mechanical mirrored swing while keeping every billboard nearly frontal.
arm_frames = (1, 9, 21, 33, 45, 49)
upper_r = (0.0, 0.65, 0.25, -0.55, -0.15, 0.0)
upper_l = (0.0, -0.55, -0.20, 0.65, 0.15, 0.0)
fore_r = (0.0, 0.30, 0.15, -0.28, -0.08, 0.0)
fore_l = (0.0, -0.25, -0.12, 0.32, 0.08, 0.0)

for index, frame in enumerate(arm_frames):
    set_rotation_z("upper_arm_r", frame, upper_r[index])
    set_rotation_z("upper_arm_l", frame, upper_l[index])
    set_rotation_z("forearm_r", frame, fore_r[index])
    set_rotation_z("forearm_l", frame, fore_l[index])


def iter_action_fcurves(generated_action: bpy.types.Action):
    # Blender 4.4+ stores curves in layered Action channel-bags.
    for layer in getattr(generated_action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channel_bag in getattr(strip, "channelbags", ()):
                yield from channel_bag.fcurves
    # Compatibility with older, non-layered Actions.
    yield from getattr(generated_action, "fcurves", ())


curve_count = 0
key_count = 0
for fcurve in iter_action_fcurves(action):
    curve_count += 1
    for keyframe in fcurve.keyframe_points:
        key_count += 1
        keyframe.interpolation = "BEZIER"
        keyframe.handle_left_type = "AUTO_CLAMPED"
        keyframe.handle_right_type = "AUTO_CLAMPED"

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = START_FRAME
scene.frame_end = END_FRAME
scene.frame_set(START_FRAME)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

result = {
    "filepath": bpy.data.filepath,
    "created_action": action.name,
    "previous_action": previous_action.name if previous_action else None,
    "frame_start": START_FRAME,
    "frame_end": END_FRAME,
    "fps": scene.render.fps,
    "curve_count": curve_count,
    "key_count": key_count,
    "active_action": animation_data.action.name if animation_data.action else None,
}
