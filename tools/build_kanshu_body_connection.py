"""Add the Kanshu body asset to the PNE View State Editor demo.

This script is intentionally non-destructive to the existing PNE head pack:
the head meshes keep their collections, materials, shape keys, and world
placement.  They are only parented to a neutral head root so the socket
hierarchy can be inspected and used later.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


SOURCE_BLEND = Path(r"C:\works\2.5D\asset\model_kanshu\kanshu_2_5d.blend")
OUTPUT_BLEND = Path(r"C:\works\2.5D\pne\_view\_state\_editor_demo.blend")
OUTPUT_DIR = OUTPUT_BLEND.parent
BODY_JSON = OUTPUT_DIR / "body_kanshu.asset.json"
BODY_GLB = OUTPUT_DIR / "body_kanshu_connection.glb"
PREVIEW_PNG = OUTPUT_DIR / "body_connection_preview.png"

BODY_COLLECTION_NAME = "ACTOR_KANSHU_BODY"
HEAD_COLLECTION_NAME = "ACTOR_KANSHU_HEAD"
DEBUG_COLLECTION_NAME = "ACTOR_KANSHU_DEBUG"

BODY_SOURCE_OBJECTS = [
    "character_root",
    "body_root",
    "torso",
    "neck",
    "upper_arm_l",
    "forearm_l",
    "hand_l",
    "upper_arm_r",
    "forearm_r",
    "hand_r",
    "spine",
    "torso_card",
    "back_arm_r",
    "ftont_arm_l",
    "back_arm_l",
    "front_arm_r",
    "neck_card",
    "hand_r_sprite",
    "hand_l_sprite",
]

RENAME_OBJECTS = {
    "character_root": "body_asset_root",
    "spine": "body_back",
    "torso_card": "torso_base",
    "back_arm_r": "upper_arm_r_back",
    "ftont_arm_l": "forearm_r_front",
    "back_arm_l": "upper_arm_l_back",
    "front_arm_r": "forearm_l_front",
    "neck_card": "neck_back",
    "hand_r_sprite": "hand_r_card",
    "hand_l_sprite": "hand_l_card",
}


def new_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def remove_collection(name: str) -> None:
    collection = bpy.data.collections.get(name)
    if collection is None:
        return
    for obj in list(collection.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def parent_keep_world(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = parent
    # Assigning matrix_parent_inverse and then matrix_world in this order can
    # collapse a newly imported object to the parent's origin in Blender 5.x.
    # Setting the world matrix after parenting is the stable keep-transform
    # operation for this authoring scene.
    obj.matrix_world = world
    bpy.context.view_layer.update()


def set_world_location(obj: bpy.types.Object, location: tuple[float, float, float]) -> None:
    """Set a location after parenting, including for nested newly linked Empties."""
    bpy.context.view_layer.update()
    matrix = obj.matrix_world.copy()
    matrix.translation = Vector(location)
    obj.matrix_world = matrix
    bpy.context.view_layer.update()


def make_empty(
    name: str,
    collection: bpy.types.Collection,
    world_location: tuple[float, float, float],
    *,
    parent: bpy.types.Object | None = None,
    display_type: str = "PLAIN_AXES",
    display_size: float = 0.22,
    hide_viewport: bool = False,
    hide_render: bool = True,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    # A direct world-matrix assignment is reliable for a newly linked Empty;
    # setting location alone can remain stale until a dependency-graph update.
    obj.matrix_world = Matrix.Translation(Vector(world_location))
    obj.empty_display_type = display_type
    obj.empty_display_size = display_size
    obj.hide_viewport = hide_viewport
    obj.hide_render = hide_render
    if parent is not None:
        bpy.context.view_layer.update()
        parent_keep_world(obj, parent)
    return obj


def make_color_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    mix = nodes.new("ShaderNodeMixShader")
    emission.inputs["Color"].default_value = color
    mix.inputs[0].default_value = color[3]
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    material.diffuse_color = color
    material.use_backface_culling = False
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
        except Exception:
            pass
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
        material.shadow_method = "NONE"
    return material


def make_polygon_mesh(
    name: str,
    vertices: list[tuple[float, float, float]],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    parent: bpy.types.Object,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [tuple(range(len(vertices)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    parent_keep_world(obj, parent)
    return obj


def append_body_objects() -> list[bpy.types.Object]:
    if not SOURCE_BLEND.exists():
        raise FileNotFoundError(SOURCE_BLEND)
    with bpy.data.libraries.load(str(SOURCE_BLEND), link=False) as (data_from, data_to):
        available = set(data_from.objects)
        data_to.objects = [name for name in BODY_SOURCE_OBJECTS if name in available]
    imported = [obj for obj in data_to.objects if obj is not None]
    missing = sorted(set(BODY_SOURCE_OBJECTS) - {obj.name for obj in imported})
    if missing:
        raise RuntimeError(f"Missing source objects: {missing}")
    return imported


def rename_imported_objects(imported: list[bpy.types.Object]) -> None:
    for old_name, new_name in RENAME_OBJECTS.items():
        obj = bpy.data.objects.get(old_name)
        if obj is None:
            raise RuntimeError(f"Expected imported object not found: {old_name}")
        if obj.type == "MESH" and obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.name = new_name
        if obj.type == "MESH":
            obj.data.name = new_name


def pack_source_body_images() -> list[str]:
    names = {
        "spine.PNG",
        "torso.PNG",
        "back_arm_r.PNG",
        "ftont_arm_l.PNG",
        "back_arm_l.PNG",
        "front_arm_r.PNG",
        "neck.PNG",
        "hand_r.PNG",
        "hand_l.PNG",
    }
    packed: list[str] = []
    for image in bpy.data.images:
        if image.name not in names:
            continue
        if image.packed_file is None:
            image.pack()
        packed.append(image.name)
    return sorted(packed)


def add_socket_metadata(obj: bpy.types.Object, **values: object) -> None:
    for key, value in values.items():
        obj[key] = value


def export_body_glb(objects: list[bpy.types.Object], filepath: Path) -> bool:
    previous_selected = list(bpy.context.selected_objects)
    previous_active = bpy.context.view_layer.objects.active
    try:
        for obj in bpy.context.view_layer.objects:
            obj.select_set(False)
        for obj in objects:
            if obj.type in {"MESH", "EMPTY"}:
                obj.hide_set(False)
                obj.select_set(True)
        root = bpy.data.objects.get("body_asset_root")
        bpy.context.view_layer.objects.active = root
        bpy.context.view_layer.update()
        try:
            bpy.ops.export_scene.gltf(
                filepath=str(filepath),
                export_format="GLB",
                use_selection=True,
                export_animations=False,
                export_skins=False,
                export_extras=True,
                export_yup=True,
                export_apply=False,
                export_image_format="AUTO",
                export_materials="EXPORT",
            )
        except TypeError:
            bpy.ops.export_scene.gltf(
                filepath=str(filepath),
                export_format="GLB",
                use_selection=True,
                export_extras=True,
            )
        return filepath.exists() and filepath.stat().st_size > 0
    finally:
        for obj in bpy.context.view_layer.objects:
            obj.select_set(False)
        for obj in previous_selected:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = previous_active


def normalize_generated_mesh_names(collection: bpy.types.Collection) -> None:
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.name = obj.name


def main() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Make reruns stable without touching any PNE collection.
    for obj in list(bpy.context.scene.objects):
        if obj.parent and obj.parent.name in {"pne_head_root", "head_pose_root"}:
            obj.parent = None
    for collection_name in (BODY_COLLECTION_NAME, HEAD_COLLECTION_NAME, DEBUG_COLLECTION_NAME):
        remove_collection(collection_name)

    body_collection = new_collection(BODY_COLLECTION_NAME)
    head_collection = new_collection(HEAD_COLLECTION_NAME)
    debug_collection = new_collection(DEBUG_COLLECTION_NAME)
    debug_collection.hide_viewport = True
    debug_collection.hide_render = True

    imported = append_body_objects()
    for obj in imported:
        body_collection.objects.link(obj)
    rename_imported_objects(imported)

    body_asset_root = bpy.data.objects["body_asset_root"]
    body_asset_root.location = (-0.43, 0.08, -5.53)
    body_asset_root.rotation_mode = "XYZ"
    body_asset_root.rotation_euler = (0.0, 0.0, 0.0)
    body_asset_root.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    actor_root = make_empty("actor_root", body_collection, (0.0, 0.0, 0.0), display_type="CIRCLE", display_size=0.35)
    actor_root.hide_viewport = True
    parent_keep_world(body_asset_root, actor_root)

    add_socket_metadata(
        body_asset_root,
        schema_version="0.1",
        body_asset_id="kanshu.stand_relaxed.front",
        body_facing_yaw_deg=0.0,
        pixels_per_unit=100.0,
        head_socket_node="head_socket",
        supported_body_loops=json.dumps(["idle", "listening", "thinking_soft"]),
        arm_left_mode="segmented",
        arm_right_mode="baked",
        render_bands=json.dumps({"body_back": 1000, "body_base": 1200, "body_motion_front": 1400}),
        motion_envelope=json.dumps({"min": [-6.05, -1.15, -8.85], "max": [4.85, 0.55, 3.25]}),
    )

    semantic_props = {
        "body_back": {"pne_body_part": "body_back", "render_band": "body_back", "render_order": 1000},
        "torso_base": {"pne_body_part": "torso_base", "render_band": "body_base", "render_order": 1200},
        "neck_back": {"pne_body_part": "neck_back", "render_band": "body_base", "render_order": 1210},
        "upper_arm_l_back": {"pne_body_part": "upper_arm_l", "arm_side": "left", "arm_segment": "upper_arm", "render_band": "body_motion_front", "render_order": 1400},
        "forearm_l_front": {"pne_body_part": "forearm_l", "arm_side": "left", "arm_segment": "forearm", "render_band": "body_motion_front", "render_order": 1410},
        "hand_l_card": {"pne_body_part": "hand_l", "arm_side": "left", "arm_segment": "hand", "render_band": "body_motion_front", "render_order": 1420},
        "upper_arm_r_back": {"pne_body_part": "upper_arm_r", "arm_side": "right", "arm_segment": "upper_arm", "render_band": "body_base", "render_order": 1220},
        "forearm_r_front": {"pne_body_part": "forearm_r", "arm_side": "right", "arm_segment": "forearm", "render_band": "body_base", "render_order": 1230},
        "hand_r_card": {"pne_body_part": "hand_r", "arm_side": "right", "arm_segment": "hand", "render_band": "body_base", "render_order": 1240},
    }
    for name, props in semantic_props.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Generated body object missing: {name}")
        for key, value in props.items():
            obj[key] = value
        obj["body_asset_id"] = "kanshu.stand_relaxed.front"

    body_root = bpy.data.objects["body_root"]
    torso = bpy.data.objects["torso"]
    neck = bpy.data.objects["neck"]
    body_root["semantic_id"] = "body_asset_root.body_root"
    torso["semantic_id"] = "torso_base"
    neck["semantic_id"] = "neck_back"

    # Meaning anchors.  The imported source body is aligned by the top of its
    # neck card; the PNE head remains at its existing origin.
    head_socket = make_empty("head_socket", body_collection, (0.0, 0.08, -2.55), parent=body_asset_root, display_type="ARROWS", display_size=0.28)
    set_world_location(head_socket, (0.0, 0.08, -2.55))
    add_socket_metadata(head_socket, semantic_id="head_socket", socket_type="head", neck_overlap_px=40, body_asset_id="kanshu.stand_relaxed.front")
    neck_back = bpy.data.objects["neck"]
    neck_back["socket_above"] = "head_socket"

    # The source arm nodes already provide the actual rigid-pivot hierarchy.
    # These markers expose the schema-required meaning sockets without
    # rewriting the authored source hierarchy.
    bpy.context.view_layer.update()
    source_pivots = {
        "shoulder_l_socket": "upper_arm_l",
        "elbow_l_socket": "forearm_l",
        "wrist_l_socket": "hand_l",
        "shoulder_r_socket": "upper_arm_r",
        "elbow_r_socket": "forearm_r",
        "wrist_r_socket": "hand_r",
    }
    socket_markers: dict[str, bpy.types.Object] = {}
    for socket_name, source_name in source_pivots.items():
        source_obj = bpy.data.objects[source_name]
        source_location = tuple(source_obj.matrix_world.translation)
        marker = make_empty(socket_name, debug_collection, source_location, parent=body_asset_root, display_type="SPHERE", display_size=0.14)
        set_world_location(marker, source_location)
        marker["semantic_id"] = socket_name
        marker["source_pivot"] = source_name
        marker["arm_side"] = "left" if socket_name.endswith("_l_socket") else "right"
        socket_markers[socket_name] = marker
    for side in ("l", "r"):
        socket_markers[f"shoulder_{side}_socket"]["safe_range_deg"] = [-8.0, 8.0]
        socket_markers[f"elbow_{side}_socket"]["safe_range_deg"] = [-12.0, 12.0]
        socket_markers[f"wrist_{side}_socket"]["safe_range_deg"] = [-15.0, 15.0]
    socket_markers["shoulder_l_socket"]["arm_mode"] = "segmented"
    socket_markers["elbow_l_socket"]["arm_mode"] = "segmented"
    socket_markers["wrist_l_socket"]["arm_mode"] = "segmented"
    for name in ("shoulder_r_socket", "elbow_r_socket", "wrist_r_socket"):
        socket_markers[name]["arm_mode"] = "baked"

    # Simple neck seam helpers.  They are deliberately separate from the
    # source texture cards so the mask/shadow can later become a runtime layer.
    skin_mat = make_color_material("actor_neck_skin", (0.78, 0.43, 0.34, 1.0))
    shadow_mat = make_color_material("actor_neck_shadow", (0.22, 0.08, 0.07, 0.42))
    neck_mask = make_polygon_mesh(
        "neck_front_mask",
        [(-1.12, 0.025, -2.53), (1.12, 0.025, -2.53), (1.42, 0.025, -3.16), (-1.42, 0.025, -3.16)],
        skin_mat,
        body_collection,
        actor_root,
    )
    neck_mask["pne_body_part"] = "neck_front_mask"
    neck_mask["render_band"] = "body_base"
    neck_mask["render_order"] = 1290
    neck_mask["purpose"] = "hide_head_neck_cut"
    neck_shadow = make_polygon_mesh(
        "neck_shadow",
        [(-1.18, -0.012, -2.56), (1.18, -0.012, -2.56), (1.04, -0.012, -2.73), (-1.04, -0.012, -2.73)],
        shadow_mat,
        body_collection,
        actor_root,
    )
    neck_shadow["pne_body_part"] = "neck_shadow"
    neck_shadow["render_band"] = "body_base"
    neck_shadow["render_order"] = 1295
    neck_shadow["opacity"] = 0.42
    body_foreground = make_empty("body_foreground", body_collection, (0.0, 0.0, 0.0), parent=actor_root, display_type="CUBE", display_size=0.12)
    body_foreground["render_band"] = "body_motion_front"
    body_foreground["render_order_range"] = [1400, 1499]

    # Runtime head hierarchy.  The inverse offset keeps the authored PNE head
    # at world origin while making head_pose_root the future motion pivot.
    head_pose_root = make_empty("head_pose_root", head_collection, (0.0, 0.0, 0.0), parent=head_socket, display_type="CIRCLE", display_size=0.30)
    set_world_location(head_pose_root, (0.0, 0.0, 0.0))
    head_pose_root["semantic_id"] = "head_pose_root"
    head_pose_root["purpose"] = "small_roll_and_breathing_only"
    pne_head_root = make_empty("pne_head_root", head_collection, (0.0, 0.0, 0.0), parent=head_pose_root, display_type="CUBE", display_size=0.18)
    set_world_location(pne_head_root, (0.0, 0.0, 0.0))
    pne_head_root["semantic_id"] = "pne_head_root"
    pne_head_root["head_view_policy"] = json.dumps({
        "allowed_view_ids": ["front_0", "front_30", "side_30"],
        "yaw_min_deg": -45,
        "yaw_max_deg": 65,
        "pitch_min_deg": -15,
        "pitch_max_deg": 20,
        "fallback_view_id": "front_30",
    })
    head_anchor = make_empty("head_neck_anchor", debug_collection, (0.0, -0.001, -2.55), parent=pne_head_root, display_type="ARROWS", display_size=0.24)
    set_world_location(head_anchor, (0.0, -0.001, -2.55))
    add_socket_metadata(head_anchor, semantic_id="head_neck_anchor", socket_type="head", anchor_owner="pne_head_pack", local_origin="head_asset")

    # Keep PNE head state meshes and all existing Shape Keys/materials intact.
    # Parenting is world-preserving and only adds the future actor hierarchy.
    head_meshes = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(obj.name.startswith(prefix) for prefix in ("BASE_", "JAW_MASK_", "EYE_", "BROW_", "MOUTH_", "OCCLUSION_"))
    ]
    for obj in head_meshes:
        parent_keep_world(obj, pne_head_root)

    # Preserve the existing head camera and add a full-actor framing camera.
    old_camera = bpy.context.scene.camera
    full_camera_data = bpy.data.cameras.get("ACTOR_Full_Camera") or bpy.data.cameras.new("ACTOR_Full_Camera")
    full_camera = bpy.data.objects.get("ACTOR_Full_Camera") or bpy.data.objects.new("ACTOR_Full_Camera", full_camera_data)
    if full_camera.name not in body_collection.objects:
        body_collection.objects.link(full_camera)
    full_camera.location = (0.0, -20.0, -5.62)
    full_camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    full_camera.data.type = "ORTHO"
    # Blender's orthographic scale is the horizontal frame size.  The target
    # demo is 16:9, so a ~30.8 horizontal scale gives ~17.3 vertical units,
    # enough for the complete head-to-feet motion envelope.
    full_camera.data.ortho_scale = 33.0
    full_camera["camera_role"] = "actor_full"
    full_camera["motion_envelope_margin_ratio"] = 0.06
    bpy.context.scene.camera = full_camera

    scene = bpy.context.scene
    scene.frame_set(1)
    scene.render.filepath = str(PREVIEW_PNG)
    scene.render.resolution_percentage = 100

    packed_images = pack_source_body_images()
    normalize_generated_mesh_names(body_collection)
    body_objects = list(body_collection.all_objects)
    glb_exported = export_body_glb(body_objects, BODY_GLB)

    body_asset = {
        "schema_version": "0.1",
        "id": "kanshu.stand_relaxed.front",
        "glb": BODY_GLB.name if glb_exported else None,
        "body_facing_yaw_deg": 0,
        "pixels_per_unit": 100,
        "head_socket": {"node": "head_socket", "scale": 1.0, "neck_overlap_px": 40},
        "head_view_policy": json.loads(pne_head_root["head_view_policy"]),
        "arms": {
            "left": {
                "mode": "segmented",
                "nodes": {"upper_arm": "upper_arm_l", "forearm": "forearm_l", "hand": "hand_l"},
                "joints": {
                    "shoulder": {"node": "shoulder_l_socket", "min_deg": -8, "max_deg": 8},
                    "elbow": {"node": "elbow_l_socket", "min_deg": -12, "max_deg": 12},
                    "wrist": {"node": "wrist_l_socket", "min_deg": -15, "max_deg": 15},
                },
            },
            "right": {"mode": "baked"},
        },
        "supported_body_loops": ["idle", "listening", "thinking_soft"],
        "motion_envelope": {"min": [-6.05, -1.15, -8.85], "max": [4.85, 0.55, 3.25], "camera_margin_ratio": 0.06},
        "composite_profile": {
            "exposure": -0.08,
            "temperature": -0.05,
            "saturation": 0.92,
            "shadow_tint": [0.10, 0.14, 0.24],
            "highlight_tint": [0.98, 0.88, 0.74],
            "neck_shadow_opacity": 0.42,
        },
        "source_blend": SOURCE_BLEND.name,
        "source_images_packed": packed_images,
        "head_pack_preserved": True,
    }
    BODY_JSON.write_text(json.dumps(body_asset, ensure_ascii=False, indent=2), encoding="utf-8")
    text_block = bpy.data.texts.get("BODY_ASSET_JSON") or bpy.data.texts.new("BODY_ASSET_JSON")
    text_block.clear()
    text_block.write(json.dumps(body_asset, ensure_ascii=False, indent=2))

    # Save before rendering so the deliverable always exists even if a render
    # backend is unavailable.  Save again after the final frame/render state.
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))

    return {
        "blend": str(OUTPUT_BLEND),
        "body_json": str(BODY_JSON),
        "body_glb": str(BODY_GLB) if glb_exported else None,
        "preview": str(PREVIEW_PNG),
        "head_meshes_parented": len(head_meshes),
        "body_objects": len([obj for obj in body_collection.all_objects if obj.type == "MESH"]),
        "body_sockets": sorted([obj.name for obj in bpy.data.objects if obj.name.endswith("_socket")]),
        "packed_images": packed_images,
        "active_camera": scene.camera.name if scene.camera else None,
        "original_camera_preserved": bool(old_camera and bpy.data.objects.get(old_camera.name)),
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
