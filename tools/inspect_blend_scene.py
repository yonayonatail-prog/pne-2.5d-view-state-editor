import bpy
import json
from pathlib import Path

scene = bpy.context.scene
result = {
    "filepath": bpy.data.filepath,
    "scene": scene.name,
    "frame": scene.frame_current,
    "frame_range": [scene.frame_start, scene.frame_end],
    "collections": [],
    "objects": [],
    "materials": [],
    "text_blocks": [text.name for text in bpy.data.texts],
}

for collection in bpy.data.collections:
    result["collections"].append({
        "name": collection.name,
        "objects": [obj.name for obj in collection.objects],
        "all_objects": [obj.name for obj in collection.all_objects],
    })

for obj in scene.objects:
    entry = {
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "parent_type": obj.parent_type,
        "location": [round(float(v), 4) for v in obj.location],
        "rotation": [round(float(v), 4) for v in obj.rotation_euler],
        "scale": [round(float(v), 4) for v in obj.scale],
        "dimensions": [round(float(v), 4) for v in obj.dimensions],
        "hide_viewport": obj.hide_viewport,
        "hide_render": obj.hide_render,
        "custom": {k: obj[k] for k in obj.keys()},
    }
    if obj.type == "MESH":
        entry["mesh_name"] = obj.data.name
        entry["vertices"] = len(obj.data.vertices)
        entry["polygons"] = len(obj.data.polygons)
        entry["materials"] = [mat.name if mat else None for mat in obj.data.materials]
        entry["shape_keys"] = [key.name for key in obj.data.shape_keys.key_blocks] if obj.data.shape_keys else []
        entry["modifiers"] = [{"name": mod.name, "type": mod.type, "object": mod.object.name if getattr(mod, "object", None) else None} for mod in obj.modifiers]
    elif obj.type == "ARMATURE":
        entry["bones"] = [bone.name for bone in obj.data.bones]
    result["objects"].append(entry)

result["materials"] = [
    {
        "name": mat.name,
        "diffuse_color": [round(float(v), 4) for v in mat.diffuse_color],
        "use_nodes": mat.use_nodes,
    }
    for mat in bpy.data.materials
]

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
