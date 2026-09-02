"""Blender integration test and inspectable demo for Trace-to-ShapeKey."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = ROOT / "blender_addon"
ARTIFACT_ROOT = ADDON_ROOT / "test_output" / "trace_to_shapekey"
SOURCE_ROOT = ARTIFACT_ROOT / "source"
EXPORT_ROOT = ARTIFACT_ROOT / "export"
BLEND_PATH = ROOT / "pne_trace_to_shapekey_demo.blend"
PREVIEW_PATH = ARTIFACT_ROOT / "trace_to_shapekey_preview.png"
sys.path.insert(0, str(ADDON_ROOT))

import pne_2_5d


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_lid_image(path: Path, phase: str, width: int = 256, height: int = 128) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new(f"trace_source_{phase}", width=width, height=height, alpha=True)
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    for x in range(24, 233):
        normalized = (x - 128.0) / 104.0
        edge_falloff = max(0.0, min(1.0, (1.0 - abs(normalized)) * 7.0))
        if phase == "open":
            center_y = 48.0 + 34.0 * (1.0 - normalized * normalized)
        elif phase == "half":
            center_y = 49.0 + 15.0 * (1.0 - normalized * normalized)
        else:
            center_y = 50.0 - 7.0 * (1.0 - normalized * normalized)
        half_width = 3.5 + 1.5 * (1.0 - normalized * normalized)
        for y in range(height):
            distance = abs(y - center_y)
            alpha = max(0.0, min(1.0, half_width + 1.0 - distance)) * edge_falloff
            if alpha <= 0.0:
                continue
            rgba[y, x, :3] = (0.015, 0.008, 0.012)
            rgba[y, x, 3] = max(rgba[y, x, 3], alpha)
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()


def prepare_source_images() -> tuple[Path, Path, Path]:
    open_path = SOURCE_ROOT / "upper_lid_open.png"
    half_path = SOURCE_ROOT / "upper_lid_half.png"
    closed_path = SOURCE_ROOT / "upper_lid_closed.png"
    write_lid_image(open_path, "open")
    write_lid_image(half_path, "half")
    write_lid_image(closed_path, "closed")
    return open_path, half_path, closed_path


def animate_shape_keys(obj: bpy.types.Object) -> None:
    keys = obj.data.shape_keys.key_blocks
    half = keys["BlinkHalf"]
    blink = keys["Blink"]
    for frame, half_value, blink_value in (
        (1, 0.0, 0.0),
        (13, 1.0, 0.0),
        (25, 0.0, 1.0),
        (37, 1.0, 0.0),
        (49, 0.0, 0.0),
    ):
        half.value = half_value
        blink.value = blink_value
        half.keyframe_insert(data_path="value", frame=frame)
        blink.keyframe_insert(data_path="value", frame=frame)


def build_contact_sheet(scene: bpy.types.Scene, source: bpy.types.Object) -> bpy.types.Collection:
    old = bpy.data.collections.get("PNE_TRACE_CONTACT_SHEET")
    if old is not None:
        for old_object in list(old.objects):
            bpy.data.objects.remove(old_object, do_unlink=True)
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("PNE_TRACE_CONTACT_SHEET")
    scene.collection.children.link(collection)
    shape_keys = source.data.shape_keys.key_blocks
    faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
    material = source.data.materials[0]
    for label, key_name, x in (
        ("OPEN / Basis", "Basis", -2.25),
        ("HALF / BlinkHalf", "BlinkHalf", 0.0),
        ("CLOSED / Blink", "Blink", 2.25),
    ):
        mesh = bpy.data.meshes.new(f"contact_{key_name.lower()}")
        mesh.from_pydata([tuple(point.co) for point in shape_keys[key_name].data], [], faces)
        mesh.update()
        mesh.materials.append(material)
        snapshot = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(snapshot)
        snapshot.location = (x, 0.0, 0.35)
        snapshot.scale = (1.35, 1.35, 1.35)

        text_data = bpy.data.curves.new(f"label_{key_name.lower()}", type="FONT")
        text_data.body = label
        text_data.align_x = "CENTER"
        text_data.size = 0.30
        text_data.extrude = 0.0
        text_data.materials.append(material)
        text_obj = bpy.data.objects.new(text_data.name, text_data)
        collection.objects.link(text_obj)
        text_obj.location = (x, -0.01, -0.75)
        text_obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)

    title_data = bpy.data.curves.new("trace_contact_title", type="FONT")
    title_data.body = "Trace-to-ShapeKey   32 stations / 64 verts / 31 quads"
    title_data.align_x = "CENTER"
    title_data.size = 0.32
    title_data.materials.append(material)
    title_obj = bpy.data.objects.new(title_data.name, title_data)
    collection.objects.link(title_obj)
    title_obj.location = (0.0, -0.01, 1.72)
    title_obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    return collection


def configure_preview(scene: bpy.types.Scene, source: bpy.types.Object) -> None:
    contact = build_contact_sheet(scene, source)
    hidden_collections: list[tuple[bpy.types.Collection, bool]] = []
    for name in ("PNE_2_5D_CHARACTER", "PNE_TRACE_PREVIEW"):
        collection = bpy.data.collections.get(name)
        if collection is not None:
            hidden_collections.append((collection, collection.hide_render))
            collection.hide_render = True
    scene.frame_start = 1
    scene.frame_end = 49
    scene.frame_set(13)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.background_type = "WORLD"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_PATH)
    scene.render.film_transparent = False
    scene.world.color = (0.74, 0.74, 0.78)
    camera = scene.camera
    require(camera is not None, "preview camera is missing")
    previous_camera_location = camera.location.copy()
    previous_camera_rotation = camera.rotation_euler.copy()
    previous_ortho_scale = camera.data.ortho_scale
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.5
    camera.location = (0.0, -12.0, 0.35)
    camera.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    bpy.ops.render.render(write_still=True)
    camera.location = previous_camera_location
    camera.rotation_euler = previous_camera_rotation
    camera.data.ortho_scale = previous_ortho_scale
    for collection, previous in hidden_collections:
        collection.hide_render = previous
    contact.hide_render = True
    contact.hide_viewport = True
    preview = bpy.data.collections.get("PNE_TRACE_PREVIEW")
    if preview is not None:
        preview.hide_render = True
        preview.hide_viewport = True


def run() -> None:
    pne_2_5d.register()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    require("FINISHED" in bpy.ops.pne.build_sample(), "sample character build failed")
    open_path, half_path, closed_path = prepare_source_images()

    scene = bpy.context.scene
    settings = scene.pne_settings
    settings.active_view_index = 0
    settings.trace_role = "UPPER_EYELID"
    settings.trace_side = "LEFT"
    settings.trace_mode = "ALPHA"
    settings.trace_threshold = 0.20
    settings.trace_min_area = 24
    settings.trace_smooth = 0.35
    settings.trace_stations = 32
    settings.trace_mesh_width = 1.45
    settings.trace_basis_image = str(open_path)
    settings.trace_half_image = str(half_path)
    settings.trace_target_image = str(closed_path)

    require("FINISHED" in bpy.ops.pne.trace_preview_paths(), "path preview failed")
    preview_collection = bpy.data.collections.get("PNE_TRACE_PREVIEW")
    require(preview_collection is not None, "preview collection was not created")
    require(sum(bool(obj.get("pne_trace_preview")) for obj in preview_collection.objects) >= 3, "normalized paths were not previewed")

    require("FINISHED" in bpy.ops.pne.trace_build_pair(), "ShapeKey pair build failed")
    obj = bpy.data.objects.get(settings.trace_output_object)
    require(obj is not None, "trace output object was not created")
    require(len(obj.data.vertices) == 64, "eyelid ribbon must contain 64 vertices")
    require(len(obj.data.polygons) == 31, "eyelid ribbon must contain 31 quads")
    require(set(obj.data.shape_keys.key_blocks.keys()) == {"Basis", "BlinkHalf", "Blink"}, "unexpected Shape Key set")
    require(obj.get("pne_topology_hash"), "topology hash is missing")
    require(float(obj.get("pne_trace_endpoint_error", 1.0)) < 1e-6, "paired endpoints were not locked")

    settings.trace_blink_preview = 0.25
    require(abs(obj.data.shape_keys.key_blocks["BlinkHalf"].value - 0.5) < 1e-6, "quarter blink does not use Half")
    require(abs(obj.data.shape_keys.key_blocks["Blink"].value) < 1e-6, "quarter blink should not use Closed")
    settings.trace_blink_preview = 0.75
    require(abs(obj.data.shape_keys.key_blocks["BlinkHalf"].value - 0.5) < 1e-6, "three-quarter blink Half weight is wrong")
    require(abs(obj.data.shape_keys.key_blocks["Blink"].value - 0.5) < 1e-6, "three-quarter blink Closed weight is wrong")

    require("FINISHED" in bpy.ops.pne.trace_assign_current_view(), "assign to current View failed")
    obj = bpy.data.objects.get(settings.trace_output_object)
    require(obj is not None and obj.name == obj.data.name, "assigned Object/Mesh names diverge")
    require(obj.get("pne_id") == "eye_l_lid_upper_line.front_0", "runtime ID is wrong")
    require(obj in bpy.data.collections["STATE_front_0"].all_objects[:], "trace object is not in front_0")
    obj.location = (-0.90, -0.004, 0.70)

    settings.blink_l = 0.75
    require(abs(obj.data.shape_keys.key_blocks["BlinkHalf"].value - 0.5) < 1e-6, "PNE Blink channel did not drive Half")
    require(abs(obj.data.shape_keys.key_blocks["Blink"].value - 0.5) < 1e-6, "PNE Blink channel did not drive Closed")

    validation = bpy.ops.pne.validate_character()
    require("FINISHED" in validation, "validator did not finish")
    require(settings.validation_summary.startswith("0 error"), f"trace character validation failed: {settings.validation_summary}")

    settings.output_directory = str(EXPORT_ROOT)
    settings.base_resolution = 64
    settings.face_resolution = 64
    settings.occlusion_resolution = 64
    settings.jaw_resolution = 64
    require("FINISHED" in bpy.ops.pne.export_runtime_bundle(), "trace runtime export failed")
    state_document = json.loads((EXPORT_ROOT / "character.states.json").read_text(encoding="utf-8"))
    front = next(view for view in state_document["views"] if view["id"] == "front_0")
    traced = next(item for item in front["objects"] if item["pne_id"] == "eye_l_lid_upper_line.front_0")
    require(traced["shape_keys"] == ["Basis", "BlinkHalf", "Blink"], "exported Shape Keys are incomplete")

    animate_shape_keys(obj)
    settings.yaw_deg = 0.0
    settings.blink_l = 0.5
    configure_preview(scene, obj)
    scene["pne_trace_demo"] = json.dumps(
        {
            "source_open": str(open_path),
            "source_half": str(half_path),
            "source_closed": str(closed_path),
            "object": obj.name,
            "frames": {"open": 1, "half": 13, "closed": 25},
            "preview": str(PREVIEW_PATH),
        },
        ensure_ascii=False,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    require(BLEND_PATH.is_file() and BLEND_PATH.stat().st_size > 100000, "demo blend was not saved")
    require(PREVIEW_PATH.is_file() and PREVIEW_PATH.stat().st_size > 1000, "preview render was not saved")
    print("PNE_TRACE_INTEGRATION_OK", BLEND_PATH, PREVIEW_PATH, len(obj.data.vertices), settings.validation_summary)


run()
