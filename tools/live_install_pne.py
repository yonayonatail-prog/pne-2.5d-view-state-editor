"""Install and stage the PNE v0.1 sample in the Blender connected over MCP."""

from __future__ import annotations

from pathlib import Path

import bpy


WORKSPACE = Path(r"C:\works\2.5D")
ARCHIVE = WORKSPACE / "blender_addon" / "dist" / "pne_2_5d_view_state_editor_v0.1.1.zip"
DEMO_BLEND = WORKSPACE / "pne_view_state_editor_demo.blend"

if not ARCHIVE.is_file():
    raise FileNotFoundError(ARCHIVE)

# An unsaved scene would place generated source textures in Blender's temporary
# directory. Give the sample a stable // project root before generation.
if not bpy.data.filepath:
    bpy.ops.wm.save_as_mainfile(filepath=str(DEMO_BLEND))

install_result = bpy.ops.preferences.addon_install(
    filepath=str(ARCHIVE),
    overwrite=True,
    enable_on_install=True,
)
if "pne_2_5d" not in bpy.context.preferences.addons:
    bpy.ops.preferences.addon_enable(module="pne_2_5d")

build_result = bpy.ops.pne.build_sample()
scene = bpy.context.scene
settings = scene.pne_settings
settings.yaw_deg = 15.0
settings.transition_mode = "DITHER"
settings.interpolation = "SMOOTHSTEP"
settings.blink_l = 0.15
settings.blink_r = 0.15
validation_result = bpy.ops.pne.validate_character()

# Put every visible 3D View into a useful authoring state without changing
# unrelated objects or deleting user data.
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        space.show_region_ui = True
        space.shading.type = "MATERIAL"
        if space.region_3d:
            space.region_3d.view_perspective = "CAMERA"

bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath or str(DEMO_BLEND))

result = {
    "install": sorted(install_result),
    "build": sorted(build_result),
    "validate": sorted(validation_result),
    "addon_enabled": "pne_2_5d" in bpy.context.preferences.addons,
    "blend": bpy.data.filepath,
    "views": [item.view_id for item in settings.views],
    "state_a": settings.state_a,
    "state_b": settings.state_b,
    "blend_value": round(settings.blend, 3),
    "transition": settings.transition_mode,
    "validation": settings.validation_summary,
    "source_root": str(Path(settings.views[0].base_texture).parents[2]) if settings.views else "",
}
