"""Add the missing hand back sprites and make relaxed-back the default.

The manually authored transforms and rigid armature binding are preserved by
duplicating the existing palm objects, then replacing only quad geometry and
materials. The malformed relaxed-back source is consumed through a cropped
derived PNG so it does not become a 5690 x 2201 runtime texture.
"""

from __future__ import annotations

from pathlib import Path

import bpy


ASSET_ROOT = Path(r"C:\works\2.5D\asset\model_anes\anes")
BLEND_PATH = ASSET_ROOT / "anes_2_5d.blend"
COLLECTION_NAME = "ANES_2_5D"
PIXELS_PER_UNIT = 100.0
PIVOT = (0.5, 0.94)


collection = bpy.data.collections.get(COLLECTION_NAME)
if collection is None:
    raise RuntimeError(f"Collection {COLLECTION_NAME!r} was not found")


def load_image(image_path: Path) -> bpy.types.Image:
    resolved = image_path.resolve()
    for image in bpy.data.images:
        if not image.filepath:
            continue
        if Path(bpy.path.abspath(image.filepath)).resolve() == resolved:
            return image
    return bpy.data.images.load(str(resolved), check_existing=True)


def make_material(image_rel: str) -> bpy.types.Material:
    image_path = ASSET_ROOT / image_rel
    image = load_image(image_path)
    image.alpha_mode = "STRAIGHT"
    material_name = f"MAT_{image_path.stem}"
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.use_nodes = True
    material.use_backface_culling = False
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"

    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    principled.inputs["Roughness"].default_value = 0.5
    tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    tree.links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return material


def set_quad_geometry(obj: bpy.types.Object, width_px: int, height_px: int) -> None:
    width = width_px / PIXELS_PER_UNIT
    height = height_px / PIXELS_PER_UNIT
    left = -PIVOT[0] * width
    right = width + left
    top = PIVOT[1] * height
    bottom = -(height - top)
    coords = (
        (left, 0.0, bottom),
        (right, 0.0, bottom),
        (right, 0.0, top),
        (left, 0.0, top),
    )
    if len(obj.data.vertices) != 4:
        raise RuntimeError(f"{obj.name!r} must remain a four-vertex sprite quad")
    for vertex, coord in zip(obj.data.vertices, coords):
        vertex.co = coord
    obj.data.update()


def configure_sprite(obj: bpy.types.Object, image_rel: str, *, visible: bool) -> None:
    image_path = ASSET_ROOT / image_rel
    image = load_image(image_path)
    width_px, height_px = int(image.size[0]), int(image.size[1])
    set_quad_geometry(obj, width_px, height_px)
    obj.data.materials.clear()
    obj.data.materials.append(make_material(image_rel))
    obj.hide_viewport = not visible
    obj.hide_render = not visible
    obj.hide_set(not visible)
    obj["part_id"] = obj.name
    obj["part_type"] = "hand"
    obj["render_order"] = 800
    obj["texture_id"] = image_path.stem
    obj["texture_path"] = image_rel.replace("\\", "/")
    obj["source_size"] = [width_px, height_px]
    obj["display_scale"] = 1.0
    obj["pivot_norm_top_left"] = list(PIVOT)
    obj["variant_group"] = "hand_l" if obj.name.startswith("hand_l") else "hand_r"
    obj["billboard_axis"] = "+Y"


def duplicate_sprite(template: bpy.types.Object, name: str) -> bpy.types.Object:
    existing = bpy.data.objects.get(name)
    if existing is not None:
        return existing
    obj = template.copy()
    obj.data = template.data.copy()
    obj.name = name
    obj.data.name = f"MESH_{name}"
    collection.objects.link(obj)
    return obj


created_or_updated: list[str] = []
for side in ("l", "r"):
    base = bpy.data.objects[f"hand_{side}"]

    relaxed_palm = duplicate_sprite(base, f"hand_{side}_variant_relaxed_palm")
    configure_sprite(relaxed_palm, "hand/hand_c_front_relaxed_palm.png", visible=False)
    created_or_updated.append(relaxed_palm.name)

    configure_sprite(base, "hand/derived/hand_c_front_relaxed_back.png", visible=True)
    created_or_updated.append(base.name)

    for gesture in ("paper", "peace", "rock", "sign"):
        palm = bpy.data.objects[f"hand_{side}_variant_{gesture}_palm"]
        back = duplicate_sprite(palm, f"hand_{side}_variant_{gesture}_back")
        configure_sprite(back, f"hand/hand_c_front_{gesture}_back.png", visible=False)
        created_or_updated.append(back.name)

    for obj in collection.all_objects:
        if not obj.name.startswith(f"hand_{side}_variant_"):
            continue
        obj.parent = base.parent
        obj.matrix_parent_inverse = base.matrix_parent_inverse.copy()
        obj.matrix_basis = base.matrix_basis.copy()

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

result = {
    "blend_file": str(BLEND_PATH),
    "created_or_updated": created_or_updated,
    "hand_objects": len(
        [obj for obj in collection.all_objects if obj.name.startswith(("hand_l", "hand_r"))]
    ),
}
