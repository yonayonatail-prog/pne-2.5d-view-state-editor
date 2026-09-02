"""Build the ANES front-view 2.5D billboard character in Blender.

This stage intentionally stops before creating an Armature.  The generated
planes, semantic hierarchy, depth ordering, materials, and pivot hints are
ready for the later bone/rig pass.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ASSET_ROOT = Path(r"C:\works\2.5D\asset\model_anes\anes")
OUTPUT_BLEND = ASSET_ROOT / "anes_2_5d.blend"
PREVIEW_PATH = ASSET_ROOT / "anes_2_5d_preview.png"
COLLECTION_NAME = "ANES_2_5D"
PIXELS_PER_UNIT = 100.0


def remove_previous_build() -> None:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        return
    for obj in list(collection.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def new_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(collection)
    return collection


def make_empty(
    name: str,
    collection: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.22
    obj.location = location
    if parent is not None:
        bpy.context.view_layer.update()
        world = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
        obj.matrix_world = world
        bpy.context.view_layer.update()
    return obj


def make_material(image_path: Path) -> bpy.types.Material:
    name = f"MAT_{image_path.stem}"
    material = bpy.data.materials.get(name)
    if material is not None:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        return material

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.use_backface_culling = False
    if hasattr(material, "surface_render_method"):
        # Blended mode is required for a stack of full-canvas PNG planes.
        # Dithered transparency writes depth for the transparent canvas and
        # punches holes through the layers behind it in Blender 5.x.
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"

    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    texture = nodes.new("ShaderNodeTexImage")

    image = bpy.data.images.get(image_path.name)
    if image is None:
        image = bpy.data.images.load(str(image_path), check_existing=True)
    image.colorspace_settings.name = "sRGB"
    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"

    material.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    return material


def parent_keep_world(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = world
    bpy.context.view_layer.update()


def make_part(
    name: str,
    image_rel: str,
    center_xz: tuple[float, float],
    depth_y: float,
    render_order: int,
    part_type: str,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    *,
    pivot_norm: tuple[float, float] = (0.5, 0.5),
    size_scale: float = 1.0,
    mirror_x: bool = False,
    rotation_y_deg: float = 0.0,
    visible: bool = True,
    variant_group: str = "",
) -> bpy.types.Object:
    image_path = ASSET_ROOT / image_rel
    image = bpy.data.images.get(image_path.name)
    if image is None:
        image = bpy.data.images.load(str(image_path), check_existing=True)
    width_px, height_px = int(image.size[0]), int(image.size[1])
    width = width_px / PIXELS_PER_UNIT * size_scale
    height = height_px / PIXELS_PER_UNIT * size_scale

    pivot_x = pivot_norm[0] * width
    pivot_from_top = pivot_norm[1] * height
    left = -pivot_x
    right = width - pivot_x
    top = pivot_from_top
    bottom = -(height - pivot_from_top)
    vertices = [
        (left, 0.0, bottom),
        (right, 0.0, bottom),
        (right, 0.0, top),
        (left, 0.0, top),
    ]
    faces = [(0, 1, 2, 3)]
    mesh = bpy.data.meshes.new(f"MESH_{name}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_coords = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_coords[loop.vertex_index]

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    # Place the image center at center_xz while keeping the object origin at
    # the future joint pivot.
    local_center_x = (0.5 - pivot_norm[0]) * width
    local_center_z = (pivot_norm[1] - 0.5) * height
    scale_x = -1.0 if mirror_x else 1.0
    rotation_y = math.radians(rotation_y_deg)
    center_offset = Matrix.Rotation(rotation_y, 4, "Y") @ Vector(
        (scale_x * local_center_x, 0.0, local_center_z)
    )
    obj.location = (
        center_xz[0] - center_offset.x,
        depth_y,
        center_xz[1] - center_offset.z,
    )
    obj.scale.x = scale_x
    obj.rotation_euler[1] = rotation_y
    obj.data.materials.append(make_material(image_path))
    parent_keep_world(obj, parent)

    obj.hide_render = not visible
    obj.hide_viewport = not visible
    obj.show_transparent = True
    obj["part_id"] = name
    obj["part_type"] = part_type
    obj["render_order"] = render_order
    obj["texture_id"] = image_path.stem
    obj["texture_path"] = image_rel.replace("\\", "/")
    obj["source_size"] = [width_px, height_px]
    obj["display_scale"] = size_scale
    obj["pivot_norm_top_left"] = [pivot_norm[0], pivot_norm[1]]
    obj["variant_group"] = variant_group
    obj["billboard_axis"] = "+Y"
    return obj


remove_previous_build()
root_collection = new_collection(COLLECTION_NAME)

# Semantic hierarchy. These are organization/pivot empties only, not bones.
character_root = make_empty("CharacterRoot", root_collection)
body_root = make_empty("BodyRoot", root_collection, character_root)
torso_root = make_empty("Torso", root_collection, body_root, (0.0, 0.0, 2.55))
neck = make_empty("Neck", root_collection, body_root, (0.0, 0.0, 4.78))
head_root = make_empty("HeadRoot", root_collection, neck, (0.0, 0.0, 4.78))

upper_arm_l_root = make_empty("UpperArm_L", root_collection, body_root, (-1.08, 0.08, 4.45))
forearm_l_root = make_empty("ForeArm_L", root_collection, upper_arm_l_root, (-1.85, 0.08, 3.25))
hand_l_root = make_empty("HandRoot_L", root_collection, forearm_l_root, (-2.12, -0.10, 1.88))
upper_arm_r_root = make_empty("UpperArm_R", root_collection, body_root, (1.08, 0.08, 4.45))
forearm_r_root = make_empty("ForeArm_R", root_collection, upper_arm_r_root, (1.85, 0.08, 3.25))
hand_r_root = make_empty("HandRoot_R", root_collection, forearm_r_root, (2.12, -0.10, 1.88))

leg_l_root = make_empty("LegRoot_L", root_collection, body_root, (-0.45, 0.09, 1.48))
foot_l_root = make_empty("FootRoot_L", root_collection, leg_l_root, (-0.45, 0.07, 1.25))
leg_r_root = make_empty("LegRoot_R", root_collection, body_root, (0.45, 0.09, 1.48))
foot_r_root = make_empty("FootRoot_R", root_collection, leg_r_root, (0.45, 0.07, 1.25))

# Back-to-front layer order. The camera sits on -Y, so smaller Y is closer.
make_part(
    "hair_back", "headhone/hair_back_c_front_base.png", (0.0, 6.15), 0.12,
    0, "hair", root_collection, head_root, pivot_norm=(0.5, 0.82), size_scale=0.85
)

make_part(
    "upper_arm_l", "upperarm/upper_arm_l_front_base.png", (-1.46, 4.10), 0.08,
    100, "body", root_collection, upper_arm_l_root, pivot_norm=(0.82, 0.12)
)
make_part(
    "forearm_l", "arm/forearm_l_front_base.png", (-1.85, 3.23), 0.08,
    110, "body", root_collection, forearm_l_root, pivot_norm=(0.50, 0.08)
)
make_part(
    "upper_arm_r", "upperarm/upper_arm_r_front_base.png", (1.46, 4.10), 0.08,
    100, "body", root_collection, upper_arm_r_root, pivot_norm=(0.18, 0.12)
)
make_part(
    "forearm_r", "arm/forearm_r_front_base.png", (1.85, 3.23), 0.08,
    110, "body", root_collection, forearm_r_root, pivot_norm=(0.50, 0.08)
)

make_part(
    "leg_l", "leg/leg_l_front_base.png", (-0.45, 1.38), 0.09,
    140, "body", root_collection, leg_l_root, pivot_norm=(0.5, 0.15)
)
make_part(
    "leg_r", "leg/leg_l_front_base.png", (0.45, 1.38), 0.09,
    140, "body", root_collection, leg_r_root, pivot_norm=(0.5, 0.15), mirror_x=True
)
make_part(
    "foot_l", "Foot/foot_l_front_base.png", (-0.45, 0.35), 0.07,
    150, "body", root_collection, foot_l_root, pivot_norm=(0.5, 0.08)
)
make_part(
    "foot_r", "Foot/foot_r_front_base.png", (0.45, 0.35), 0.07,
    150, "body", root_collection, foot_r_root, pivot_norm=(0.5, 0.08)
)

make_part(
    "torso_lower", "spine/spine_c_front_base.png", (0.0, 2.55), 0.06,
    200, "body", root_collection, torso_root, pivot_norm=(0.5, 0.82)
)
make_part(
    "torso_upper", "chest/chest_c_front_base.png", (0.0, 4.10), 0.05,
    210, "body", root_collection, torso_root, pivot_norm=(0.5, 0.84)
)

face_center = (0.0, 6.20)
make_part(
    "face_base", "F_face/face_composite_c_front_normal.png", face_center, 0.00,
    500, "face", root_collection, head_root, pivot_norm=(0.5, 0.90),
    variant_group="expression"
)

expression_files = [
    "blush", "happening", "sad", "shobon", "shock", "smile", "sweat", "ugly"
]
for index, expression in enumerate(expression_files):
    make_part(
        f"face_variant_{expression}",
        f"F_face/face_composite_c_front_{expression}.png",
        face_center,
        -0.001 - index * 0.0001,
        500,
        "face",
        root_collection,
        head_root,
        pivot_norm=(0.5, 0.90),
        visible=False,
        variant_group="expression",
    )

make_part(
    "hair_side", "hair_side_c_front_base.png", (0.0, 6.23), -0.02,
    690, "hair", root_collection, head_root, pivot_norm=(0.5, 0.86)
)
make_part(
    "hair_front", "hair_front_c_front_base.png", (0.0, 7.22), -0.04,
    700, "hair", root_collection, head_root, pivot_norm=(0.5, 0.90)
)
make_part(
    "headphone", "headhone/headphone_c_front_base.png", (0.0, 7.15), -0.06,
    900, "accessory", root_collection, head_root, pivot_norm=(0.5, 0.90)
)
make_part(
    "headphone_spindles", "perker_spindle_c_front_base.png", (0.0, 4.78), -0.08,
    910, "accessory", root_collection, head_root, pivot_norm=(0.5, 0.10)
)

hand_l_base = make_part(
    "hand_l", "hand/derived/hand_c_front_relaxed_back.png", (-2.12, 1.15), -0.10,
    800, "hand", root_collection, hand_l_root, pivot_norm=(0.5, 0.94),
    mirror_x=True, rotation_y_deg=180.0, variant_group="hand_l"
)
hand_l_base["handedness"] = "left"
hand_l_base["source_hand"] = "right"

hand_r_base = make_part(
    "hand_r", "hand/derived/hand_c_front_relaxed_back.png", (2.12, 1.15), -0.10,
    800, "hand", root_collection, hand_r_root, pivot_norm=(0.5, 0.94),
    rotation_y_deg=180.0, variant_group="hand_r"
)
hand_r_base["handedness"] = "right"
hand_r_base["source_hand"] = "right"

hand_variants = [
    "relaxed_palm",
    "paper_palm", "paper_back",
    "peace_palm", "peace_back",
    "rock_palm", "rock_back",
    "sign_palm", "sign_back",
]
for side, x, parent, mirror, handedness in (
    ("l", -2.12, hand_l_root, True, "left"),
    ("r", 2.12, hand_r_root, False, "right"),
):
    for index, variant in enumerate(hand_variants):
        variant_obj = make_part(
            f"hand_{side}_variant_{variant}",
            f"hand/hand_c_front_{variant}.png",
            (x, 1.15),
            -0.101 - index * 0.0001,
            800,
            "hand",
            root_collection,
            parent,
            pivot_norm=(0.5, 0.94),
            mirror_x=mirror,
            rotation_y_deg=180.0,
            visible=False,
            variant_group=f"hand_{side}",
        )
        variant_obj["handedness"] = handedness
        variant_obj["source_hand"] = "right"

# Build metadata on the root for runtime/export tooling.
character_root["schema_version"] = "0.1"
character_root["build_stage"] = "pre_bone"
character_root["billboard"] = True
character_root["front_axis"] = "-Y_camera_to_+Y"
character_root["pixels_per_unit"] = PIXELS_PER_UNIT
character_root["source_asset_root"] = str(ASSET_ROOT)
character_root["notes"] = "Planes/materials/hierarchy/pivot hints complete; no Armature created."

# Dedicated orthographic preview camera; preserve the original scene camera.
camera_data = bpy.data.cameras.get("ANES_CameraData") or bpy.data.cameras.new("ANES_CameraData")
camera = bpy.data.objects.get("ANES_Camera")
if camera is None:
    camera = bpy.data.objects.new("ANES_Camera", camera_data)
    root_collection.objects.link(camera)
camera.location = (0.0, -30.0, 4.20)
camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
camera.data.type = "ORTHO"
camera.data.ortho_scale = 11.2
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 768
scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = str(PREVIEW_PATH)
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "Medium High Contrast"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

# Save a new file, leaving the small source .blend untouched.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
# Eevee's object-level alpha sorting can change with overlapping billboard
# bounds.  Use Cycles only for the deterministic QA still, then restore Eevee
# for the lightweight authoring scene.
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.use_denoising = False
bpy.ops.render.render(write_still=True)
scene.render.engine = "BLENDER_EEVEE"
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))

visible_meshes = [
    obj.name for obj in root_collection.all_objects
    if obj.type == "MESH" and not obj.hide_render
]
hidden_variants = [
    obj.name for obj in root_collection.all_objects
    if obj.type == "MESH" and obj.hide_render
]
result = {
    "output_blend": str(OUTPUT_BLEND),
    "preview": str(PREVIEW_PATH),
    "collection": COLLECTION_NAME,
    "visible_mesh_count": len(visible_meshes),
    "hidden_variant_count": len(hidden_variants),
    "visible_meshes": visible_meshes,
    "armatures": [obj.name for obj in root_collection.all_objects if obj.type == "ARMATURE"],
}
