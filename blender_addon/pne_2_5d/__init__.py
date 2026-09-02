"""PNE 2.5D View State Editor.

The add-on keeps authoring data in the Blender Scene, previews adjacent view
states with a complementary dither mask, and exports a small Three.js-ready
runtime bundle.
"""

from __future__ import annotations

bl_info = {
    "name": "PNE 2.5D View State Editor",
    "author": "PNE",
    "version": (0, 1, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > PNE 2.5D",
    "description": "Author, validate, preview, and export multi-view 2.5D characters",
    "category": "3D View",
}

from .operators import OPERATOR_CLASSES
from .properties import PROPERTY_CLASSES, register_scene_properties, unregister_scene_properties
from .ui import UI_CLASSES


CLASSES = (*PROPERTY_CLASSES, *OPERATOR_CLASSES, *UI_CLASSES)


def register() -> None:
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_scene_properties()


def unregister() -> None:
    import bpy

    unregister_scene_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
