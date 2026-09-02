from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


path = Path(sys.argv[1])
with path.open("rb") as handle:
    magic, version, length = struct.unpack("<4sII", handle.read(12))
    if magic != b"glTF":
        raise RuntimeError("Not a binary glTF file")
    chunk_length, chunk_type = struct.unpack("<II", handle.read(8))
    if chunk_type != 0x4E4F534A:
        raise RuntimeError("First GLB chunk is not JSON")
    document = json.loads(handle.read(chunk_length).decode("utf-8").rstrip("\x00 "))

materials = document.get("materials", [])
summary = {
    "path": str(path),
    "bytes": length,
    "materials": len(materials),
    "images": len(document.get("images", [])),
    "textures": len(document.get("textures", [])),
    "animations": [animation.get("name") for animation in document.get("animations", [])],
    "skins": len(document.get("skins", [])),
    "all_alpha_blend": all(material.get("alphaMode") == "BLEND" for material in materials),
    "all_have_base_color_texture": all(
        "baseColorTexture" in material.get("pbrMetallicRoughness", {})
        for material in materials
    ),
    "emissive_materials": [
        material.get("name")
        for material in materials
        if "emissiveTexture" in material or material.get("emissiveFactor")
    ],
    "unlit_materials": [
        material.get("name")
        for material in materials
        if "KHR_materials_unlit" in material.get("extensions", {})
    ],
    "material_sample": [
        {
            "name": material.get("name"),
            "alphaMode": material.get("alphaMode"),
            "doubleSided": material.get("doubleSided"),
            "baseColorTexture": material.get("pbrMetallicRoughness", {}).get("baseColorTexture"),
            "metallicFactor": material.get("pbrMetallicRoughness", {}).get("metallicFactor"),
            "roughnessFactor": material.get("pbrMetallicRoughness", {}).get("roughnessFactor"),
        }
        for material in materials[:5]
    ],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
