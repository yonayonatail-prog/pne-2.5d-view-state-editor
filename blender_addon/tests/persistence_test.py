"""Load the integration .blend in a fresh process and confirm persisted state."""

from __future__ import annotations

from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "blender_addon"))
import pne_2_5d


pne_2_5d.register()
blend_path = ROOT / "blender_addon" / "test_output" / "pne_integration.blend"
bpy.ops.wm.open_mainfile(filepath=str(blend_path))
settings = bpy.context.scene.pne_settings
if len(settings.views) != 4:
    raise AssertionError("View States did not persist")
if settings.views[0].view_id != "front_0":
    raise AssertionError("View IDs did not persist")
if abs(settings.blink_l - 0.7) > 0.001:
    raise AssertionError("Expression state did not persist")
if bpy.data.texts.get("PNE_DEBUG_LOG") is None:
    raise AssertionError("PNE_DEBUG_LOG did not persist")
print("PNE_PERSISTENCE_OK", len(settings.views), settings.state_a, settings.state_b)
