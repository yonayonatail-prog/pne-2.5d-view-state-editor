from pathlib import Path

import bpy


COLLECTION_NAME = "ANES_2_5D"
BLEND_PATH = Path(r"C:\works\2.5D\asset\model_anes\anes\anes_2_5d.blend")
SCREENSHOT_PATH = Path(r"C:\works\2.5D\asset\model_anes\anes\after_principled_fix.png")

collection = bpy.data.collections.get(COLLECTION_NAME)
if collection is None:
    raise RuntimeError(f"Collection {COLLECTION_NAME!r} was not found")

mesh_objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
used_materials = []
for obj in mesh_objects:
    for slot in obj.material_slots:
        if slot.material and slot.material not in used_materials:
            used_materials.append(slot.material)

fixed = []
skipped = []
for material in used_materials:
    material.use_nodes = True
    tree = material.node_tree
    image_nodes = [node for node in tree.nodes if node.bl_idname == "ShaderNodeTexImage" and node.image]
    if not image_nodes:
        skipped.append(material.name)
        continue

    image = image_nodes[0].image
    image.alpha_mode = "STRAIGHT"
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.name = "Material Output"
    output.location = (480, 40)

    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "Principled BSDF"
    principled.location = (100, 40)
    principled.inputs["Roughness"].default_value = 0.5

    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.name = "Sprite Texture"
    texture.label = Path(bpy.path.abspath(image.filepath)).name
    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    texture.location = (-300, 40)

    tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    tree.links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
    material.use_backface_culling = False
    material.diffuse_color[3] = 1.0
    fixed.append({
        "material": material.name,
        "image": bpy.path.abspath(image.filepath),
        "links": [
            "Sprite Texture.Color -> Principled BSDF.Base Color",
            "Sprite Texture.Alpha -> Principled BSDF.Alpha",
            "Principled BSDF.BSDF -> Material Output.Surface",
        ],
    })

renamed_mesh_data = []
shared_mesh_data = []
for obj in mesh_objects:
    if obj.data.name == obj.name:
        continue
    if obj.data.users == 1:
        old_name = obj.data.name
        obj.data.name = obj.name
        renamed_mesh_data.append({"object": obj.name, "old_data": old_name})
    else:
        shared_mesh_data.append({
            "object": obj.name,
            "data": obj.data.name,
            "users": obj.data.users,
        })

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

hidden = {}
selected = [obj for obj in bpy.context.selected_objects]
active = bpy.context.view_layer.objects.active
try:
    for obj in bpy.context.scene.objects:
        hidden[obj.name] = obj.hide_get()
        obj.select_set(False)
        if obj.type in {"ARMATURE", "CAMERA", "LIGHT", "EMPTY"}:
            obj.hide_set(True)
    for obj in mesh_objects:
        obj.hide_set(False)
        obj.select_set(True)
    if mesh_objects:
        bpy.context.view_layer.objects.active = mesh_objects[0]
    bpy.context.view_layer.update()

    for area in bpy.context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        area.spaces.active.overlay.show_relationship_lines = False
        for region in area.regions:
            if region.type != "WINDOW":
                continue
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_axis(type="FRONT", align_active=False)
                bpy.ops.view3d.view_selected(use_all_regions=False)
            break
    bpy.ops.screen.screenshot(filepath=str(SCREENSHOT_PATH))
finally:
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
        if obj.name in hidden:
            obj.hide_set(hidden[obj.name])
    for obj in selected:
        if obj.name in bpy.context.view_layer.objects:
            obj.select_set(True)
    bpy.context.view_layer.objects.active = active
    bpy.context.view_layer.update()

result = {
    "blend_file": bpy.data.filepath,
    "fixed_count": len(fixed),
    "fixed": fixed,
    "skipped": skipped,
    "renamed_mesh_data": renamed_mesh_data,
    "shared_mesh_data": shared_mesh_data,
    "screenshot": str(SCREENSHOT_PATH),
    "screenshot_size": SCREENSHOT_PATH.stat().st_size if SCREENSHOT_PATH.exists() else 0,
}
