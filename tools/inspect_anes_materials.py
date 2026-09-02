from pathlib import Path

import bpy


screenshot_path = Path(r"C:\works\2.5D\asset\model_anes\anes\before_material_fix.png")
screenshot_error = None
try:
    bpy.ops.screen.screenshot(filepath=str(screenshot_path))
except Exception as exc:
    screenshot_error = repr(exc)

objects = []
for obj in bpy.context.scene.objects:
    objects.append({
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "dimensions": [round(v, 4) for v in obj.dimensions],
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "modifiers": [modifier.type for modifier in obj.modifiers],
    })

materials = []
for material in bpy.data.materials:
    nodes = []
    links = []
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            node_info = {"name": node.name, "type": node.bl_idname}
            if node.bl_idname == "ShaderNodeTexImage":
                node_info["image"] = node.image.filepath if node.image else None
            nodes.append(node_info)
        for link in material.node_tree.links:
            links.append({
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.name,
            })
    materials.append({
        "name": material.name,
        "blend_method": getattr(material, "surface_render_method", getattr(material, "blend_method", None)),
        "nodes": nodes,
        "links": links,
    })

result = {
    "blend_file": bpy.data.filepath,
    "frame": bpy.context.scene.frame_current,
    "collections": [collection.name for collection in bpy.data.collections],
    "objects": objects,
    "materials": materials,
    "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
    "screenshot_error": screenshot_error,
}
