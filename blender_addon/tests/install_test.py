"""Install the distributed ZIP into an isolated Blender user scripts folder."""

from __future__ import annotations

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[2]
archive = ROOT / "blender_addon" / "dist" / "pne_2_5d_view_state_editor_v0.1.1.zip"
if not archive.is_file():
    raise AssertionError(f"Missing archive: {archive}")

result = bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True, enable_on_install=True)
if "FINISHED" not in result:
    raise AssertionError(f"Install failed: {result}")
if "pne_2_5d" not in bpy.context.preferences.addons:
    enable_result = bpy.ops.preferences.addon_enable(module="pne_2_5d")
    if "FINISHED" not in enable_result:
        raise AssertionError(f"Enable failed: {enable_result}")
if "pne_2_5d" not in bpy.context.preferences.addons:
    raise AssertionError("Installed add-on is not enabled")
if not hasattr(bpy.context.scene, "pne_settings"):
    raise AssertionError("Scene properties were not registered")
print("PNE_INSTALL_OK", archive, bpy.context.preferences.addons["pne_2_5d"].module)
