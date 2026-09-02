"""Runtime texture and GLB/state bundle export."""

from __future__ import annotations

from array import array
import json
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Iterable

import bpy

from .constants import ADDON_VERSION, ROLE_CONCEPT_Z, ROLE_RENDER_ORDER, SCHEMA_VERSION
from .runtime import view_objects
from .validator import validate_character


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _rgba8_dfd() -> bytes:
    """KHR Data Format Descriptor for an uncompressed RGBA8 texture."""

    samples = bytearray()
    for bit_offset, channel in ((0, 0), (8, 1), (16, 2), (24, 15)):
        samples.extend(struct.pack("<HBB4BII", bit_offset, 7, channel, 0, 0, 0, 0, 0, 255))
    descriptor_size = 24 + len(samples)
    total_size = 4 + descriptor_size
    return b"".join(
        (
            struct.pack("<I", total_size),
            struct.pack("<HHHH", 0, 0, 2, descriptor_size),
            bytes((1, 1, 1, 0)),
            bytes((0, 0, 0, 0)),
            bytes((4, 0, 0, 0, 0, 0, 0, 0)),
            bytes(samples),
        )
    )


def write_uncompressed_ktx2(image: bpy.types.Image, path: Path) -> None:
    """Write a standards-based RGBA8 KTX2 fallback without changing source data."""

    width, height = int(image.size[0]), int(image.size[1])
    floats = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(floats)
    raw = bytearray(len(floats))
    for index, value in enumerate(floats):
        raw[index] = max(0, min(255, round(float(value) * 255.0)))

    dfd = _rgba8_dfd()
    level_index_offset = 80
    dfd_offset = level_index_offset + 24
    level_offset = _align(dfd_offset + len(dfd), 8)
    identifier = b"\xABKTX 20\xBB\r\n\x1A\n"
    # VK_FORMAT_R8G8B8A8_UNORM = 37. No supercompression is used in fallback mode.
    header = struct.pack(
        "<12s13I2Q",
        identifier,
        37,
        1,
        width,
        height,
        0,
        0,
        1,
        1,
        0,
        dfd_offset,
        len(dfd),
        0,
        0,
        0,
        0,
    )
    level_index = struct.pack("<3Q", level_offset, len(raw), len(raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(level_index)
        handle.write(dfd)
        handle.write(b"\0" * (level_offset - handle.tell()))
        handle.write(raw)


def _encoder_path(settings) -> Path | None:
    if settings.ktx2_encoder:
        candidate = Path(bpy.path.abspath(settings.ktx2_encoder))
        return candidate if candidate.is_file() else None
    found = shutil.which("toktx")
    return Path(found) if found else None


def _encode_ktx2(image: bpy.types.Image, png_path: Path, ktx_path: Path, mipmap: bool, settings) -> str:
    encoder = _encoder_path(settings)
    if encoder is not None and encoder.name.lower().startswith("toktx"):
        command = [str(encoder), "--t2", "--encode", "basis-lz"]
        if mipmap:
            command.append("--genmipmap")
        command.extend([str(ktx_path), str(png_path)])
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode == 0 and ktx_path.is_file():
            return "KTX2_BASIS_LZ"
    write_uncompressed_ktx2(image, ktx_path)
    return "KTX2_RGBA8_FALLBACK"


def _copy_resize_image(source_path: Path, output_path: Path, resolution: int) -> bpy.types.Image:
    source = bpy.data.images.load(str(source_path), check_existing=True)
    runtime = source.copy()
    runtime.name = f"PNE_RUNTIME_{source.name}_{resolution}"
    if int(runtime.size[0]) != resolution or int(runtime.size[1]) != resolution:
        runtime.scale(resolution, resolution)
    runtime.filepath_raw = str(output_path)
    runtime.file_format = "PNG"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.save()
    return runtime


def _texture_sources(state) -> tuple[tuple[str, str], ...]:
    return (
        ("base", state.base_texture),
        ("face_parts", state.face_parts_texture),
        ("occlusion", state.occlusion_texture),
        ("jaw", state.jaw_texture),
    )


def build_runtime_assets(scene: bpy.types.Scene) -> tuple[Path, dict]:
    settings = scene.pne_settings
    root = Path(bpy.path.abspath(settings.output_directory))
    texture_root = root / "textures"
    resolutions = {
        "base": settings.base_resolution,
        "face_parts": settings.face_resolution,
        "occlusion": settings.occlusion_resolution,
        "jaw": settings.jaw_resolution,
    }
    manifest: dict = {"schema_version": SCHEMA_VERSION, "views": {}, "encoders": {}}
    for state in settings.views:
        view_manifest: dict = {}
        memory_bytes = 0
        for pack, raw_path in _texture_sources(state):
            source_path = Path(bpy.path.abspath(raw_path))
            if not source_path.is_file():
                raise FileNotFoundError(f"Missing source texture: {source_path}")
            output_dir = texture_root / state.view_id
            png_path = output_dir / f"{pack}.png"
            ktx_path = output_dir / f"{pack}.ktx2"
            runtime = _copy_resize_image(source_path, png_path, resolutions[pack])
            mipmap = settings.mipmap_base if pack == "base" else settings.mipmap_face if pack == "face_parts" else False
            encoder = _encode_ktx2(runtime, png_path, ktx_path, mipmap, settings)
            memory_bytes += ktx_path.stat().st_size
            view_manifest[pack] = {
                "source": source_path.as_posix(),
                "preview": png_path.relative_to(root).as_posix(),
                "runtime": ktx_path.relative_to(root).as_posix(),
                "resolution": [resolutions[pack], resolutions[pack]],
                "mipmap": mipmap,
                "format": encoder,
            }
            manifest["encoders"][encoder] = manifest["encoders"].get(encoder, 0) + 1
            bpy.data.images.remove(runtime)
        state.estimated_memory_mb = memory_bytes / (1024.0 * 1024.0)
        manifest["views"][state.view_id] = view_manifest
    root.mkdir(parents=True, exist_ok=True)
    with (root / "texture_build.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    return root, manifest


def _object_record(obj: bpy.types.Object) -> dict:
    role = str(obj.get("pne_role", ""))
    return {
        "pne_id": str(obj.get("pne_id", "")),
        "role": role,
        "view_id": str(obj.get("pne_view_id", "")),
        "render_order": int(obj.get("pne_render_order", ROLE_RENDER_ORDER.get(role, 0))),
        "concept_z": float(obj.get("pne_concept_z", ROLE_CONCEPT_Z.get(role, 0.0))),
        "texture_pack": str(obj.get("pne_texture_pack", "")),
        "shape_keys": list(getattr(getattr(obj.data, "shape_keys", None), "key_blocks", {}).keys()),
    }


def build_state_document(scene: bpy.types.Scene, texture_manifest: dict) -> dict:
    settings = scene.pne_settings
    views = []
    expression_mapping: dict[str, list[str]] = {
        "blink_l": [],
        "blink_r": [],
        "brow": [],
        "mouth_open": [],
        "smile": [],
        "jaw": [],
    }
    for state in sorted(settings.views, key=lambda item: (item.yaw_deg, item.view_id)):
        objects = [_object_record(obj) for obj in view_objects(scene, state.view_id) if obj.type == "MESH"]
        for item in objects:
            role = item["role"]
            if role == "eye_l":
                expression_mapping["blink_l"].append(item["pne_id"])
            elif role == "eye_r":
                expression_mapping["blink_r"].append(item["pne_id"])
            elif role.startswith("brow_"):
                expression_mapping["brow"].append(item["pne_id"])
            elif role == "mouth":
                expression_mapping["mouth_open"].append(item["pne_id"])
                expression_mapping["smile"].append(item["pne_id"])
            elif role == "jaw":
                expression_mapping["jaw"].append(item["pne_id"])
        views.append(
            {
                "id": state.view_id,
                "yaw_deg": state.yaw_deg,
                "pitch_deg": state.pitch_deg,
                "flip_x": state.flip_x,
                "mirror_source": state.mirror_source or None,
                "collection": state.collection_name,
                "estimated_memory_mb": round(state.estimated_memory_mb, 3),
                "textures": texture_manifest["views"].get(state.view_id, {}),
                "objects": objects,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "addon_version": ADDON_VERSION,
        "character_id": settings.character_id,
        "glb": "character.glb",
        "views": views,
        "transition": {
            "default_mode": "DITHER",
            "supported_modes": ["STEP", "SHARP", "DITHER", "ALPHA"],
            "interpolation": settings.interpolation.lower(),
            "expression_sync": True,
        },
        "render_roles": {role: {"render_order": order, "concept_z": ROLE_CONCEPT_Z[role]} for role, order in ROLE_RENDER_ORDER.items()},
        "texture_policy": {
            "active_views": settings.active_views,
            "prefetch_views": settings.prefetch_views,
            "cache_views": settings.cache_views,
            "max_gpu_memory_mb": settings.max_gpu_memory_mb,
        },
        "texture_build": {"encoders": texture_manifest.get("encoders", {})},
        "expression_mapping": expression_mapping,
        "resident_at_export": {
            "active": settings.resident_active.split(",") if settings.resident_active else [],
            "prefetch": settings.resident_prefetch.split(",") if settings.resident_prefetch else [],
            "cache": settings.resident_cache.split(",") if settings.resident_cache else [],
        },
    }


def _export_glb(scene: bpy.types.Scene, path: Path) -> None:
    selected_before = list(bpy.context.selected_objects)
    active_before = bpy.context.view_layer.objects.active
    collection_visibility: dict[str, tuple[bool, bool]] = {}
    try:
        bpy.ops.object.select_all(action="DESELECT")
        objects: list[bpy.types.Object] = []
        for state in scene.pne_settings.views:
            collection = bpy.data.collections.get(state.collection_name)
            if collection is None:
                continue
            collection_visibility[collection.name] = (collection.hide_viewport, collection.hide_render)
            collection.hide_viewport = False
            collection.hide_render = False
            for obj in collection.all_objects:
                if obj.type == "MESH":
                    obj.hide_set(False)
                    obj.select_set(True)
                    objects.append(obj)
        if objects:
            bpy.context.view_layer.objects.active = objects[0]
        operator = bpy.ops.export_scene.gltf
        properties = set(operator.get_rna_type().properties.keys())
        candidates = {
            "filepath": str(path),
            "export_format": "GLB",
            "use_selection": True,
            "export_extras": True,
            "export_morph": True,
            "export_yup": True,
            "export_apply": False,
        }
        kwargs = {key: value for key, value in candidates.items() if key in properties}
        result = operator(**kwargs)
        if "FINISHED" not in result:
            raise RuntimeError(f"GLB export did not finish: {result}")
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected_before:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = active_before
        for name, visibility in collection_visibility.items():
            collection = bpy.data.collections.get(name)
            if collection:
                collection.hide_viewport, collection.hide_render = visibility


def export_runtime_bundle(scene: bpy.types.Scene) -> tuple[Path, Path, Path]:
    issues = validate_character(scene, update_ui=True)
    errors = [item for item in issues if item.severity == "ERROR"]
    if errors:
        raise RuntimeError(f"Validation failed with {len(errors)} error(s)")
    root, texture_manifest = build_runtime_assets(scene)
    glb_path = root / "character.glb"
    json_path = root / "character.states.json"
    _export_glb(scene, glb_path)
    document = build_state_document(scene, texture_manifest)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
    return root, glb_path, json_path
