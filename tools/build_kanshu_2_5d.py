"""Build the Kanshu 2.5D cutout character pack in Blender.

This is intentionally a light-weight, front-facing 2.5D pack.  The source
PNG files are kept as individual cards for authoring, while an atlas and JSON
metadata are written for the Three.js runtime.  The source illustration is
kept as a hidden reference card and is not used as the rendered character.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


SOURCE_ROOT = Path(r"C:\works\pne\台本\audio_projects\看守\看守\2.5D\img\kanshu")
OUTPUT_ROOT = Path(r"C:\works\2.5D\asset\model_kanshu")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

BLEND_PATH = OUTPUT_ROOT / "kanshu_2_5d.blend"
GLB_PATH = OUTPUT_ROOT / "kanshu_2_5d.glb"
PREVIEW_PATH = OUTPUT_ROOT / "kanshu_2_5d_preview.png"
ATLAS_PATH = OUTPUT_ROOT / "atlas.png"
ATLAS_JSON_PATH = OUTPUT_ROOT / "atlas.json"
CHARACTER_JSON_PATH = OUTPUT_ROOT / "character.json"
ANIMATION_JSON_PATH = OUTPUT_ROOT / "animation.json"

COLLECTION_NAME = "Kanshu_2_5D"
REFERENCE_COLLECTION_NAME = "Kanshu_Reference"
PIXELS_PER_UNIT = 100.0
CANVAS_W = 1024.0
CANVAS_H = 1536.0

PARTS: list[dict] = []
ATLAS_SOURCES: dict[str, Path] = {}


def world_from_px(x: float, y: float) -> tuple[float, float, float]:
    """Convert top-left image pixels into Blender X/Y/Z coordinates."""

    return ((x - CANVAS_W / 2.0) / PIXELS_PER_UNIT, 0.0, (CANVAS_H / 2.0 - y) / PIXELS_PER_UNIT)


def remove_collection(name: str) -> None:
    collection = bpy.data.collections.get(name)
    if collection is None:
        return
    for obj in list(collection.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def new_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def parent_keep_world(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = world
    bpy.context.view_layer.update()


def make_empty(
    name: str,
    collection: bpy.types.Collection,
    location_px: tuple[float, float] = (CANVAS_W / 2.0, CANVAS_H / 2.0),
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    x, _, z = world_from_px(*location_px)
    obj.location = (x, 0.0, z)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.18
    if parent is not None:
        parent_keep_world(obj, parent)
    obj["semantic_id"] = name
    return obj


def set_blended(mat: bpy.types.Material) -> None:
    mat.use_nodes = True
    mat.use_backface_culling = False
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
        mat.shadow_method = "NONE"


def image_material(image_path: Path) -> bpy.types.Material:
    name = "mat_" + image_path.stem.lower().replace(" ", "_")
    material = bpy.data.materials.get(name)
    if material is not None:
        return material

    material = bpy.data.materials.new(name)
    set_blended(material)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    texture = nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.colorspace_settings.name = "sRGB"
    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    links.new(texture.outputs["Color"], emission.inputs["Color"])
    links.new(texture.outputs["Alpha"], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    material["source_path"] = image_path.as_posix()
    return material


def color_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    set_blended(material)
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = color[3]
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    material.diffuse_color = color
    return material


def mesh_card(
    name: str,
    image_path: Path,
    center_px: tuple[float, float],
    depth_y: float,
    render_order: int,
    part_type: str,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    *,
    size_scale: float = 1.0,
    mirror_x: bool = False,
    visible: bool = True,
    variant_group: str = "",
    add_blink_shape: bool = False,
    part_id: str | None = None,
) -> bpy.types.Object:
    image = bpy.data.images.load(str(image_path), check_existing=True)
    width_px, height_px = int(image.size[0]), int(image.size[1])
    width = width_px / PIXELS_PER_UNIT * size_scale
    height = height_px / PIXELS_PER_UNIT * size_scale
    vertices = [
        (-width / 2.0, 0.0, -height / 2.0),
        (width / 2.0, 0.0, -height / 2.0),
        (width / 2.0, 0.0, height / 2.0),
        (-width / 2.0, 0.0, height / 2.0),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_coords = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_coords[loop.vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    world_x, _, world_z = world_from_px(*center_px)
    obj.location = (world_x, depth_y, world_z)
    if mirror_x:
        obj.scale.x = -1.0
    obj.data.materials.append(image_material(image_path))
    parent_keep_world(obj, parent)
    obj.hide_render = not visible
    obj.hide_viewport = not visible
    obj.show_transparent = True
    semantic_id = part_id or name
    obj["part_id"] = semantic_id
    obj["part_type"] = part_type
    obj["render_order"] = render_order
    obj["asset_id"] = image_path.stem.lower()
    obj["source_path"] = image_path.as_posix()
    obj["source_size"] = [width_px, height_px]
    obj["pivot"] = [0.5, 0.5]
    obj["variant_group"] = variant_group
    obj["billboard_axis"] = "+Y"
    if add_blink_shape:
        obj.shape_key_add(name="Basis")
        blink = obj.shape_key_add(name="blink")
        for vertex in blink.data:
            vertex.co.z *= 0.08
        obj.data.shape_keys.key_blocks["blink"].value = 0.0
        obj["shape_key_channel"] = "blink"
    PARTS.append(
        {
            "id": semantic_id,
            "type": part_type,
            "asset_id": image_path.stem.lower(),
            "source_path": image_path.name,
            "node": parent.name,
            "depth": depth_y,
            "render_order": render_order,
            "source_size": [width_px, height_px],
            "pivot": [0.5, 0.5],
            "flip_x": mirror_x,
            "visible": visible,
            "variant_group": variant_group,
        }
    )
    ATLAS_SOURCES[image_path.stem.lower()] = image_path
    return obj


def simple_quad(
    name: str,
    center_px: tuple[float, float],
    size_px: tuple[float, float],
    depth_y: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
    *,
    visible: bool = True,
) -> bpy.types.Object:
    width, height = size_px[0] / PIXELS_PER_UNIT, size_px[1] / PIXELS_PER_UNIT
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(-width / 2, 0, -height / 2), (width / 2, 0, -height / 2), (width / 2, 0, height / 2), (-width / 2, 0, height / 2)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    x, _, z = world_from_px(*center_px)
    obj.location = (x, depth_y, z)
    obj.data.materials.append(material)
    parent_keep_world(obj, parent)
    obj.hide_render = not visible
    obj.hide_viewport = not visible
    obj["part_id"] = name
    obj["part_type"] = "face_overlay"
    obj["opacity_driver"] = "anger"
    return obj


def add_shape_key(obj: bpy.types.Object, key_name: str = "blink") -> None:
    obj.shape_key_add(name="Basis")
    key = obj.shape_key_add(name=key_name)
    for vertex in key.data:
        vertex.co.z *= 0.08
    obj.data.shape_keys.key_blocks[key_name].value = 0.0


def add_rig(collection: bpy.types.Collection) -> bpy.types.Object:
    arm_data = bpy.data.armatures.new("kanshu_armature")
    armature = bpy.data.objects.new("kanshu_armature", arm_data)
    collection.objects.link(armature)
    armature.show_in_front = False
    armature["schema_version"] = "0.2"
    armature["rig_type"] = "2.5d_cutout"
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    def add_bone(name: str, head_px: tuple[float, float], tail_px: tuple[float, float], parent: str | None = None) -> None:
        bone = arm_data.edit_bones.new(name)
        hx, _, hz = world_from_px(*head_px)
        tx, _, tz = world_from_px(*tail_px)
        bone.head = (hx, 0.0, hz)
        bone.tail = (tx, 0.0, tz)
        if parent:
            bone.parent = arm_data.edit_bones.get(parent)

    add_bone("root", (512, 1460), (512, 1360))
    add_bone("pelvis", (512, 1170), (512, 970), "root")
    add_bone("torso", (512, 970), (512, 650), "pelvis")
    add_bone("neck", (555, 650), (555, 570), "torso")
    add_bone("head", (555, 570), (555, 260), "neck")
    add_bone("upper_arm_l", (730, 690), (850, 820), "torso")
    add_bone("forearm_l", (850, 820), (895, 1010), "upper_arm_l")
    add_bone("hand_l", (895, 1010), (850, 1120), "forearm_l")
    add_bone("upper_arm_r", (360, 700), (220, 820), "torso")
    add_bone("forearm_r", (220, 820), (160, 590), "upper_arm_r")
    add_bone("hand_r", (160, 590), (300, 300), "forearm_r")
    add_bone("eye_l", (625, 390), (645, 390), "head")
    add_bone("eye_r", (485, 390), (465, 390), "head")
    add_bone("hair_side_lock_l_root", (735, 360), (760, 450), "head")
    add_bone("hair_side_lock_l_mid", (760, 450), (770, 560), "hair_side_lock_l_root")
    add_bone("hair_side_lock_l_tip", (770, 560), (760, 670), "hair_side_lock_l_mid")
    add_bone("hair_side_lock_r_root", (390, 350), (370, 450), "head")
    add_bone("hair_side_lock_r_mid", (370, 450), (360, 560), "hair_side_lock_r_root")
    add_bone("hair_side_lock_r_tip", (360, 560), (370, 660), "hair_side_lock_r_mid")
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    armature["bone_roles"] = json.dumps(
        {
            "face": ["head", "eye_l", "eye_r"],
            "body": ["root", "pelvis", "torso", "neck"],
            "arms": ["upper_arm_l", "forearm_l", "hand_l", "upper_arm_r", "forearm_r", "hand_r"],
            "hair": [
                "hair_side_lock_l_root", "hair_side_lock_l_mid", "hair_side_lock_l_tip",
                "hair_side_lock_r_root", "hair_side_lock_r_mid", "hair_side_lock_r_tip",
            ],
        },
        ensure_ascii=False,
    )
    return armature


def keyframe_rotation(obj: bpy.types.Object, frame: int, degrees: float) -> None:
    obj.rotation_mode = "XYZ"
    obj.rotation_euler[1] = math.radians(degrees)
    obj.keyframe_insert(data_path="rotation_euler", index=1, frame=frame)


def keyframe_visibility(obj: bpy.types.Object, frame: int, hidden: bool) -> None:
    obj.hide_render = hidden
    obj.keyframe_insert(data_path="hide_render", frame=frame)


def make_atlas() -> dict:
    sources = sorted(ATLAS_SOURCES.items())
    max_width = 2048
    padding = 3
    x = padding
    y = padding
    row_height = 0
    placements: dict[str, dict] = {}
    for asset_id, path in sorted(sources, key=lambda item: (-int(bpy.data.images.load(str(item[1]), check_existing=True).size[1]), item[0])):
        image = bpy.data.images.load(str(path), check_existing=True)
        width, height = int(image.size[0]), int(image.size[1])
        if x + width + padding > max_width:
            x = padding
            y += row_height + padding
            row_height = 0
        placements[asset_id] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "source_size": [width, height],
            "source_rect": [0, 0, width, height],
            "trimmed": False,
            "source_path": path.name,
        }
        x += width + padding
        row_height = max(row_height, height)
    atlas_height = y + row_height + padding
    atlas_height = max(1, int(math.ceil(atlas_height / 4.0) * 4))
    atlas = bpy.data.images.new("kanshu_atlas", width=max_width, height=atlas_height, alpha=True)
    atlas_pixels = [0.0] * (max_width * atlas_height * 4)
    for asset_id, placement in placements.items():
        image = bpy.data.images.load(str(ATLAS_SOURCES[asset_id]), check_existing=True)
        width, height = placement["width"], placement["height"]
        pixels = [0.0] * (width * height * 4)
        image.pixels.foreach_get(pixels)
        for row in range(height):
            src_start = row * width * 4
            dst_start = ((placement["y"] + row) * max_width + placement["x"]) * 4
            atlas_pixels[dst_start : dst_start + width * 4] = pixels[src_start : src_start + width * 4]
    atlas.pixels.foreach_set(atlas_pixels)
    atlas.filepath_raw = str(ATLAS_PATH)
    atlas.file_format = "PNG"
    atlas.save()
    metadata = {
        "schema_version": "2.0",
        "atlas": {
            "image": ATLAS_PATH.name,
            "width": max_width,
            "height": atlas_height,
            "padding": padding,
            "extrude": True,
            "trim": True,
            "square": False,
        },
        "sprites": placements,
    }
    ATLAS_JSON_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def write_json_files(atlas_metadata: dict, root: bpy.types.Object, armature: bpy.types.Object) -> None:
    nodes = {
        "character_root": {"parent": None, "type": "group"},
        "body_root": {"parent": "character_root", "type": "group"},
        "torso": {"parent": "body_root", "type": "group"},
        "neck": {"parent": "body_root", "type": "group"},
        "head_root": {"parent": "neck", "type": "group"},
        "face_root": {"parent": "head_root", "type": "group"},
        "eye_socket_l": {"parent": "face_root", "type": "group"},
        "eye_socket_r": {"parent": "face_root", "type": "group"},
        "eye_ball_l": {"parent": "eye_socket_l", "type": "group", "bone": "eye_l"},
        "eye_ball_r": {"parent": "eye_socket_r", "type": "group", "bone": "eye_r"},
        "brow_l": {"parent": "face_root", "type": "sprite"},
        "brow_r": {"parent": "face_root", "type": "sprite"},
        "brow_glabella_crease": {"parent": "face_root", "type": "overlay"},
        "mouth": {"parent": "face_root", "type": "sprite"},
        "hair_back": {"parent": "head_root", "type": "sprite"},
        "hair_side_lock_l": {"parent": "head_root", "type": "group", "bone": "hair_side_lock_l_root"},
        "hair_side_lock_r": {"parent": "head_root", "type": "group", "bone": "hair_side_lock_r_root"},
        "hair_front": {"parent": "head_root", "type": "sprite"},
        "accessories": {"parent": "head_root", "type": "group"},
        "upper_arm_l": {"parent": "body_root", "type": "group", "bone": "upper_arm_l"},
        "forearm_l": {"parent": "upper_arm_l", "type": "group", "bone": "forearm_l"},
        "hand_l": {"parent": "forearm_l", "type": "group", "bone": "hand_l"},
        "upper_arm_r": {"parent": "body_root", "type": "group", "bone": "upper_arm_r"},
        "forearm_r": {"parent": "upper_arm_r", "type": "group", "bone": "forearm_r"},
        "hand_r": {"parent": "forearm_r", "type": "group", "bone": "hand_r"},
    }
    character = {
        "version": "0.2",
        "type": "character_pack",
        "character_id": "kanshu",
        "display_name": "看守",
        "source_reference": "mihon.png",
        "atlas": "atlas.json",
        "glb": GLB_PATH.name,
        "coordinate_system": {"plane": "XZ", "camera_axis": "-Y", "depth_axis": "Y", "pixels_per_unit": PIXELS_PER_UNIT},
        "nodes": nodes,
        "parts": PARTS,
        "anchors": {
            "head_center": [552, 420],
            "neck": [560, 620],
            "eye_socket_l": [628, 388],
            "eye_socket_r": [486, 390],
            "mouth_center": [530, 475],
            "shoulder_l": [735, 700],
            "shoulder_r": [335, 700],
            "hand_l": [790, 1140],
            "hand_r": [350, 270],
        },
        "bones": [bone.name for bone in armature.data.bones],
        "morph_targets": ["blink_l", "blink_r"],
        "capabilities": {
            "blink": True,
            "mouth_shapes": ["normal", "closed", "lagph", "sad", "small_open"],
            "brow": True,
            "glabella_crease": True,
            "hair_physics": True,
            "body_motion": True,
            "compound_clip": True,
            "inference": True,
        },
        "physics": {"stiffness": 0.72, "damping": 0.18, "gravity": 0.05, "wind": 0.02, "max_angle": 8},
    }
    CHARACTER_JSON_PATH.write_text(json.dumps(character, ensure_ascii=False, indent=2), encoding="utf-8")
    animation = {
        "version": "0.2",
        "character_id": "kanshu",
        "clips": [
            {
                "type": "compound_clip",
                "id": "blink",
                "duration": 0.16,
                "tracks": [
                    {"target": "face.eye_l", "channel": "blink", "keys": [{"time": 0.0, "value": 0.0}, {"time": 0.08, "value": 1.0, "ease": "power2.inOut"}, {"time": 0.16, "value": 0.0, "ease": "power2.out"}]},
                    {"target": "face.eye_r", "channel": "blink", "keys": [{"time": 0.0, "value": 0.0}, {"time": 0.08, "value": 1.0, "ease": "power2.inOut"}, {"time": 0.16, "value": 0.0, "ease": "power2.out"}]},
                ],
            },
            {
                "type": "compound_clip",
                "id": "angry",
                "duration": 0.30,
                "tracks": [
                    {"target": "face.brow_l", "property": "rotation.z", "keys": [{"time": 0.0, "value": 0}, {"time": 0.18, "value": -14, "ease": "power2.out"}]},
                    {"target": "face.brow_r", "property": "rotation.z", "keys": [{"time": 0.0, "value": 0}, {"time": 0.18, "value": 14, "ease": "power2.out"}]},
                    {"target": "face.brow_glabella_crease", "property": "opacity", "keys": [{"time": 0.0, "value": 0}, {"time": 0.12, "value": 1, "ease": "power2.out"}]},
                    {"target": "face.mouth", "property": "texture", "keys": [{"time": 0.0, "value": "normal"}, {"time": 0.18, "value": "sad"}]},
                ],
            },
        ],
        "tracks": [
            {"target": "body.head", "property": "rotation.y", "keys": [{"time": 0.0, "value": 0.0}, {"time": 0.5, "value": 1.2}, {"time": 1.0, "value": -1.0}, {"time": 1.5, "value": 0.0}]},
            {"target": "hair_side_lock_l", "property": "rotation.y", "keys": [{"time": 0.0, "value": 0.0}, {"time": 0.5, "value": 3.0}, {"time": 1.0, "value": -2.0}, {"time": 1.5, "value": 0.0}]},
        ],
        "nodes": [
            {"type": "SetNode", "id": "mouth_shape", "target": "face.mouth"},
            {"type": "TweenNode", "id": "blink_tween", "target": "face.eye_l.blink"},
            {"type": "SpriteNode", "id": "mouth_sprite", "target": "face.mouth"},
            {"type": "MorphNode", "id": "blink_morph", "target": "face.eye_l.blink"},
            {"type": "PhysicsNode", "id": "hair_spring", "target": "hair_side_lock_l"},
            {"type": "InferenceNode", "id": "voice_expression", "model": "MorphTargetInference", "outputs": {"mouth_open": "face.mouth.open", "eye_open_l": "face.eye_l.open", "eye_open_r": "face.eye_r.open"}},
        ],
    }
    ANIMATION_JSON_PATH.write_text(json.dumps(animation, ensure_ascii=False, indent=2), encoding="utf-8")


def export_glb(collection: bpy.types.Collection, armature: bpy.types.Object) -> None:
    export_objects = [obj for obj in collection.all_objects if obj.type in {"MESH", "EMPTY", "ARMATURE"}]
    previous_selection = list(bpy.context.selected_objects)
    previous_active = bpy.context.view_layer.objects.active
    visibility = {obj.name: (obj.hide_viewport, obj.hide_render, obj.hide_get()) for obj in export_objects}
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
            filepath=str(GLB_PATH),
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
            old_viewport, old_render, old_hide = visibility[obj.name]
            obj.hide_viewport = old_viewport
            obj.hide_render = old_render
            obj.hide_set(old_hide)
        for obj in previous_selection:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = previous_active
        bpy.context.view_layer.update()


def normalize_mesh_datablock_names(collection: bpy.types.Collection) -> None:
    # Rebuilding in the same Blender session leaves old zero-user mesh blocks
    # behind.  Remove those first so the current export has stable ASCII names.
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.name = obj.name


remove_collection(COLLECTION_NAME)
remove_collection(REFERENCE_COLLECTION_NAME)
main_collection = new_collection(COLLECTION_NAME)
reference_collection = new_collection(REFERENCE_COLLECTION_NAME)

# Keep original scene objects intact but make the authored camera the render camera.
for obj in bpy.context.scene.objects:
    if obj.type in {"CAMERA", "LIGHT"}:
        obj.hide_render = True
        obj.hide_viewport = True

character_root = make_empty("character_root", main_collection, (512, 768))
body_root = make_empty("body_root", main_collection, (512, 1060), character_root)
torso_root = make_empty("torso", main_collection, (540, 930), body_root)
neck_root = make_empty("neck", main_collection, (555, 610), body_root)
head_root = make_empty("head_root", main_collection, (555, 420), neck_root)
face_root = make_empty("face_root", main_collection, (555, 420), head_root)
eye_socket_l = make_empty("eye_socket_l", main_collection, (628, 388), face_root)
eye_socket_r = make_empty("eye_socket_r", main_collection, (486, 390), face_root)
eye_ball_l = make_empty("eye_ball_l", main_collection, (628, 388), eye_socket_l)
eye_ball_r = make_empty("eye_ball_r", main_collection, (486, 390), eye_socket_r)
brow_l = make_empty("brow_l", main_collection, (486, 340), face_root)
brow_r = make_empty("brow_r", main_collection, (628, 335), face_root)
mouth_root = make_empty("mouth", main_collection, (530, 475), face_root)
hair_back_root = make_empty("hair_back", main_collection, (700, 340), head_root)
hair_side_l = make_empty("hair_side_lock_l", main_collection, (735, 350), head_root)
hair_side_r = make_empty("hair_side_lock_r", main_collection, (400, 350), head_root)
hair_front_root = make_empty("hair_front", main_collection, (555, 300), head_root)
accessories_root = make_empty("accessories", main_collection, (555, 250), head_root)
upper_arm_l_root = make_empty("upper_arm_l", main_collection, (750, 700), body_root)
forearm_l_root = make_empty("forearm_l", main_collection, (850, 850), upper_arm_l_root)
hand_l_root = make_empty("hand_l", main_collection, (790, 1140), forearm_l_root)
upper_arm_r_root = make_empty("upper_arm_r", main_collection, (340, 700), body_root)
forearm_r_root = make_empty("forearm_r", main_collection, (220, 700), upper_arm_r_root)
hand_r_root = make_empty("hand_r", main_collection, (350, 270), forearm_r_root)

def src(name: str) -> Path:
    path = SOURCE_ROOT / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


# Back-to-front cards.  Image coordinates were authored against mihon.png.
mesh_card("spine", src("spine.PNG"), (540, 1110), 0.24, 100, "body", main_collection, torso_root, size_scale=1.0)
mesh_card("torso_card", src("torso.PNG"), (550, 875), 0.20, 110, "body", main_collection, torso_root, size_scale=1.0, part_id="torso")
# The source filenames follow the character-side naming in the layered art:
# back_arm_r is the raised screen-left sleeve, while back_arm_l carries the
# red armband on screen-right.
mesh_card("back_arm_r", src("back_arm_r.PNG"), (185, 620), 0.18, 120, "body", main_collection, upper_arm_r_root, size_scale=1.0)
mesh_card("ftont_arm_l", src("ftont_arm_l.PNG"), (300, 790), 0.16, 130, "body", main_collection, forearm_r_root, size_scale=0.92)
mesh_card("back_arm_l", src("back_arm_l.PNG"), (870, 795), 0.15, 120, "body", main_collection, upper_arm_l_root, size_scale=1.0)
mesh_card("front_arm_r", src("front_arm_r.PNG"), (835, 1010), 0.13, 130, "body", main_collection, forearm_l_root, size_scale=1.0)
mesh_card("neck_card", src("neck.PNG"), (570, 620), 0.07, 300, "body", main_collection, neck_root, size_scale=1.0, part_id="neck")

face = mesh_card("face_base", src("face_base.PNG"), (550, 420), 0.02, 400, "face", main_collection, face_root, size_scale=1.0)
mesh_card("hair_back_card", src("hair_back.PNG"), (705, 330), 0.00, 500, "hair", main_collection, hair_back_root, size_scale=1.0, part_id="hair_back")
mesh_card("hair_front_side", src("hair_front_side.PNG"), (700, 340), -0.02, 510, "hair", main_collection, hair_side_l, size_scale=1.0)
mesh_card("hair_braised", src("hair_braised.PNG"), (770, 620), -0.04, 520, "hair", main_collection, hair_side_l, size_scale=0.86)
mesh_card("hair_front_card", src("hair_front.PNG"), (500, 290), -0.06, 530, "hair", main_collection, hair_front_root, size_scale=1.0, part_id="hair_front")
mesh_card("accessory_hair", src("accessory_hair.PNG"), (790, 700), -0.08, 540, "accessory", main_collection, accessories_root, size_scale=1.0)
mesh_card("hat", src("hat.PNG"), (560, 110), -0.10, 550, "accessory", main_collection, accessories_root, size_scale=1.0)

# Face sprites: left/right logical nodes are character-side names, not screen-side names.
mesh_card("eye_l_sclera", src("eye_l_sclera.PNG"), (486, 390), -0.04, 600, "eye", main_collection, eye_socket_r, size_scale=1.0)
mesh_card("eye_r_sclera", src("eye_r_sclera.PNG"), (628, 385), -0.04, 600, "eye", main_collection, eye_socket_l, size_scale=1.0)
eye_l_core = mesh_card("eye_l_core", src("eye_core.PNG"), (486, 390), -0.06, 610, "eye", main_collection, eye_ball_r, size_scale=0.44)
eye_r_core = mesh_card("eye_r_core", src("eye_core.PNG"), (628, 385), -0.06, 610, "eye", main_collection, eye_ball_l, size_scale=0.44, mirror_x=True)
mesh_card("eye_l_highlight", src("eye_l_highlight.PNG"), (491, 384), -0.08, 620, "eye", main_collection, eye_ball_r, size_scale=0.46)
mesh_card("eye_r_highlight", src("eye_l_highlight.PNG"), (633, 379), -0.08, 620, "eye", main_collection, eye_ball_l, size_scale=0.46, mirror_x=True)
mesh_card("eye_l_lid_upper_line", src("eye_l_lid_upper_line.PNG"), (486, 373), -0.10, 630, "eyelid", main_collection, eye_socket_r, size_scale=0.98, add_blink_shape=True)
mesh_card("eye_r_lid_upper_line", src("eye_r_lid_upper_line.PNG"), (628, 370), -0.10, 630, "eyelid", main_collection, eye_socket_l, size_scale=0.98, add_blink_shape=True)
mesh_card("eye_l_lid_lower_line", src("eye_l_lod_lower_line.PNG"), (490, 409), -0.10, 631, "eyelid", main_collection, eye_socket_r, size_scale=0.98)
mesh_card("eye_r_lid_lower_line", src("eye_r_lod_lower_line.PNG"), (640, 404), -0.10, 631, "eyelid", main_collection, eye_socket_l, size_scale=0.40)
mesh_card("eye_r_lid_upper_detail", src("eye_r_lid_upper_line_ridline.PNG"), (651, 371), -0.11, 632, "eyelid", main_collection, eye_socket_l, size_scale=0.9)
mesh_card("brow_l_sprite", src("brow_l.PNG"), (486, 335), -0.12, 640, "brow", main_collection, brow_l, size_scale=1.0, part_id="brow_l")
mesh_card("brow_r_sprite", src("brow_r.PNG"), (628, 330), -0.12, 640, "brow", main_collection, brow_r, size_scale=1.0, part_id="brow_r")

for mouth_name, visible, depth in (
    ("mouth", True, -0.14),
    ("mouth_closed", False, -0.141),
    ("mouth_lagph", False, -0.142),
    ("mouth_sad", False, -0.143),
    ("mouth_small_open", False, -0.144),
):
    obj = mesh_card(
        "mouth_sprite" if mouth_name == "mouth" else "mouth_variant_" + mouth_name.removeprefix("mouth_"),
        src(mouth_name + ".PNG"),
        (530, 475),
        depth,
        650,
        "mouth",
        main_collection,
        mouth_root,
        size_scale=1.0,
        visible=visible,
        variant_group="mouth",
        part_id="mouth" if mouth_name == "mouth" else "mouth_variant_" + mouth_name.removeprefix("mouth_"),
    )

# Hands intentionally sit in front of sleeves.
mesh_card("hand_r_sprite", src("hand_r.PNG"), (350, 270), -0.16, 700, "hand", main_collection, hand_r_root, size_scale=0.90, part_id="hand_r")
mesh_card("hand_l_sprite", src("hand_l.PNG"), (790, 1140), -0.16, 700, "hand", main_collection, hand_l_root, size_scale=0.90, part_id="hand_l")

# Face overlays required by v0.2.  The crease starts transparent and is driven by anger.
crease_mat = color_material("mat_brow_glabella_crease", (0.24, 0.07, 0.04, 0.0))
crease = simple_quad("brow_glabella_crease", (555, 350), (18, 3), -0.18, crease_mat, main_collection, face_root, visible=True)
crease["default_opacity"] = 0.0
crease["channel"] = "anger"
add_shape_key(crease, "anger")
lid_fill_mat = color_material("mat_eye_lid_upper_fill", (0.94, 0.60, 0.43, 0.0))
lid_fill_l = simple_quad("eye_l_lid_upper_fill", (486, 390), (62, 28), -0.035, lid_fill_mat, main_collection, eye_socket_r, visible=True)
lid_fill_r = simple_quad("eye_r_lid_upper_fill", (628, 385), (52, 27), -0.035, lid_fill_mat, main_collection, eye_socket_l, visible=True)
add_shape_key(lid_fill_l, "blink")
add_shape_key(lid_fill_r, "blink")

armature = add_rig(main_collection)

# Store binding hints on cards without forcing the authoring scene through a heavy skin setup.
bone_by_node = {
    "head_root": "head",
    "eye_ball_l": "eye_l",
    "eye_ball_r": "eye_r",
    "hair_side_lock_l": "hair_side_lock_l_root",
    "hair_side_lock_r": "hair_side_lock_r_root",
    "upper_arm_l": "upper_arm_l",
    "forearm_l": "forearm_l",
    "hand_l": "hand_l",
    "upper_arm_r": "upper_arm_r",
    "forearm_r": "forearm_r",
    "hand_r": "hand_r",
}
for obj in main_collection.all_objects:
    if obj.type == "MESH" and obj.parent and obj.parent.name in bone_by_node:
        obj["bound_bone"] = bone_by_node[obj.parent.name]

# Idle and blink authoring keys on the lightweight semantic nodes.
scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 49
scene.frame_set(1)
for frame, value in ((1, 0.0), (13, 0.0), (17, 1.0), (21, 0.0), (49, 0.0)):
    for obj in (bpy.data.objects.get("eye_l_lid_upper_line"), bpy.data.objects.get("eye_r_lid_upper_line"), lid_fill_l, lid_fill_r):
        if obj and obj.data.shape_keys:
            obj.data.shape_keys.key_blocks["blink"].value = value
            obj.data.shape_keys.key_blocks["blink"].keyframe_insert(data_path="value", frame=frame)
for frame, degrees in ((1, 0.0), (13, 1.2), (25, 0.0), (37, -1.0), (49, 0.0)):
    keyframe_rotation(head_root, frame, degrees)
for frame, degrees in ((1, 0.0), (13, 3.0), (25, -2.0), (37, 2.0), (49, 0.0)):
    keyframe_rotation(hair_side_l, frame, degrees)
    keyframe_rotation(hair_side_r, frame, -degrees * 0.8)
for frame, degrees in ((1, 0.0), (13, -0.6), (25, 0.0), (37, 0.5), (49, 0.0)):
    keyframe_rotation(torso_root, frame, degrees)

for pb_name in ("head", "hair_side_lock_l_root", "hair_side_lock_l_mid", "hair_side_lock_l_tip", "hair_side_lock_r_root", "hair_side_lock_r_mid", "hair_side_lock_r_tip"):
    pb = armature.pose.bones.get(pb_name)
    if pb is None:
        continue
    pb.rotation_mode = "XYZ"
    for frame, degrees in ((1, 0.0), (13, 2.0), (25, -1.5), (37, 1.0), (49, 0.0)):
        pb.rotation_euler[1] = math.radians(degrees if "_l_" in pb_name else -degrees)
        pb.keyframe_insert(data_path="rotation_euler", index=1, frame=frame, group=pb_name)

# Hidden reference image for authoring alignment; it never goes into the render or GLB.
reference_parent = make_empty("reference_guide", reference_collection, (512, 768))
reference = mesh_card("mihon_reference", SOURCE_ROOT / "mihon.png", (512, 768), 0.8, 0, "reference", reference_collection, reference_parent, size_scale=1.0, visible=False)
reference["guide_only"] = True

character_root["schema_version"] = "0.2"
character_root["build_stage"] = "atlas_rig_ready"
character_root["billboard"] = True
character_root["front_axis"] = "-Y_camera_to_+Y"
character_root["pixels_per_unit"] = PIXELS_PER_UNIT
character_root["source_asset_root"] = str(SOURCE_ROOT)
character_root["spec"] = "2.5D立ち絵システム仕様書 v0.2"
character_root["atlas"] = ATLAS_JSON_PATH.name
character_root["character_json"] = CHARACTER_JSON_PATH.name
character_root["animation_json"] = ANIMATION_JSON_PATH.name
character_root["physics_method"] = "spring_overlay_ready"

# Preview camera uses the exact reference aspect ratio.
camera_data = bpy.data.cameras.new("kanshu_preview_camera")
camera = bpy.data.objects.new("kanshu_preview_camera", camera_data)
main_collection.objects.link(camera)
camera.location = (0.0, -30.0, 0.0)
camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
camera.data.type = "ORTHO"
camera.data.ortho_scale = 16.2
scene.camera = camera
scene.render.resolution_x = 768
scene.render.resolution_y = 1152
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.world.use_nodes = True
world_background = scene.world.node_tree.nodes.get("Background")
if world_background is not None:
    world_background.inputs["Color"].default_value = (0.08, 0.012, 0.006, 1.0)
    world_background.inputs["Strength"].default_value = 0.35
scene.world.color = (0.08, 0.012, 0.006)
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = str(PREVIEW_PATH)
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "Medium High Contrast"
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine = "BLENDER_EEVEE"

atlas_metadata = make_atlas()
write_json_files(atlas_metadata, character_root, armature)
normalize_mesh_datablock_names(main_collection)
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
export_glb(main_collection, armature)
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

result = {
    "blend": str(BLEND_PATH),
    "glb": str(GLB_PATH),
    "preview": str(PREVIEW_PATH),
    "atlas": str(ATLAS_PATH),
    "atlas_json": str(ATLAS_JSON_PATH),
    "character_json": str(CHARACTER_JSON_PATH),
    "animation_json": str(ANIMATION_JSON_PATH),
    "parts": len([obj for obj in main_collection.all_objects if obj.type == "MESH"]),
    "empties": len([obj for obj in main_collection.all_objects if obj.type == "EMPTY"]),
    "bones": len(armature.data.bones),
    "atlas_sprites": len(atlas_metadata["sprites"]),
    "scene": scene.name,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
