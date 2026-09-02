"""Headless Blender integration test for the installable PNE add-on."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = ROOT / "blender_addon"
ARTIFACT_ROOT = ROOT / "blender_addon" / "test_output"
sys.path.insert(0, str(ADDON_ROOT))

import pne_2_5d
from pne_2_5d.core import ViewPoint, compute_residency, resolve_view_blend


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    pne_2_5d.register()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    blend_path = ARTIFACT_ROOT / "pne_integration.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    result = bpy.ops.pne.build_sample()
    require("FINISHED" in result, "sample builder did not finish")
    scene = bpy.context.scene
    settings = scene.pne_settings
    require(len(settings.views) == 4, "sample must contain four views")

    settings.yaw_deg = 15.0
    require(settings.state_a == "front_0" and settings.state_b == "front_30", "yaw pair is incorrect")
    require(0.49 < settings.blend < 0.51, "15 degree blend should be 0.5")
    settings.blink_l = 0.7
    for view_id in (settings.state_a, settings.state_b):
        collection = bpy.data.collections["STATE_" + view_id]
        eye = next(obj for obj in collection.all_objects if obj.get("pne_role") == "eye_l")
        require(abs(eye.data.shape_keys.key_blocks["Blink"].value - 0.7) < 0.001, "expression is not synchronized")

    result = bpy.ops.pne.validate_character()
    require("FINISHED" in result and settings.validation_summary.startswith("0 error"), "sample validation failed")

    settings.output_directory = str(ARTIFACT_ROOT / "export")
    settings.base_resolution = 64
    settings.face_resolution = 64
    settings.occlusion_resolution = 64
    settings.jaw_resolution = 64
    result = bpy.ops.pne.export_runtime_bundle()
    require("FINISHED" in result, "runtime bundle export failed")

    export_root = ARTIFACT_ROOT / "export"
    glb_path = export_root / "character.glb"
    json_path = export_root / "character.states.json"
    require(glb_path.is_file() and glb_path.stat().st_size > 1024, "GLB was not created")
    require(json_path.is_file(), "state JSON was not created")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    require(len(document["views"]) == 4, "export JSON view count is incorrect")
    require(document["transition"]["default_mode"] == "DITHER", "DITHER is not the runtime default")
    require(document["texture_policy"]["active_views"] == 2, "texture residency policy is missing")
    for view in document["views"]:
        require(len(view["objects"]) >= 8, f"{view['id']} lacks runtime objects")
        for pack in ("base", "face_parts", "occlusion", "jaw"):
            ktx = export_root / view["textures"][pack]["runtime"]
            require(ktx.is_file(), f"missing KTX2: {ktx}")
            require(ktx.read_bytes()[:12] == b"\xABKTX 20\xBB\r\n\x1A\n", f"invalid KTX2 identifier: {ktx}")

    blend = resolve_view_blend(45.0, [ViewPoint("a", 30), ViewPoint("b", 60)], "LINEAR")
    require(blend.state_a == "a" and blend.state_b == "b" and blend.blend == 0.5, "core interpolation failed")
    residency = compute_residency(["a", "b", "c", "d"], "a", "b", ("d",), 1, 2)
    require(residency.active == ("a", "b") and residency.prefetch == ("c",), "residency calculation failed")

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print("PNE_INTEGRATION_OK", glb_path.stat().st_size, json_path)


run()
