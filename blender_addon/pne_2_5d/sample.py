"""Procedural four-view sample character builder."""

from __future__ import annotations

import math
from pathlib import Path

import bpy

from .constants import MASTER_COLLECTION, ROLE_CONCEPT_Z, ROLE_RENDER_ORDER, ROLE_TEXTURE_PACK
from .materials import create_dither_material


SAMPLE_VIEWS = (
    ("front_0", 0.0),
    ("front_30", 30.0),
    ("side_30", 60.0),
    ("side_0", 90.0),
)


def _remove_collection(collection: bpy.types.Collection) -> None:
    children = list(collection.children)
    for child in children:
        _remove_collection(child)
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def clear_sample() -> None:
    collection = bpy.data.collections.get(MASTER_COLLECTION)
    if collection is not None:
        _remove_collection(collection)
    for material in list(bpy.data.materials):
        if material.get("pne_material"):
            bpy.data.materials.remove(material)


def _new_collection(name: str, parent: bpy.types.Collection) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def _mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    collection: bpy.types.Collection,
    role: str,
    view_id: str,
    color: tuple[float, float, float, float],
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj["pne_id"] = f"{role}.{view_id}"
    obj["pne_role"] = role
    obj["pne_view_id"] = view_id
    obj["pne_render_order"] = ROLE_RENDER_ORDER[role]
    obj["pne_concept_z"] = ROLE_CONCEPT_Z[role]
    obj["pne_texture_pack"] = ROLE_TEXTURE_PACK[role]
    obj["pne_uv_padding"] = 32
    obj["pne_sample"] = True
    obj.hide_render = False
    material = create_dither_material(f"PNE_{view_id}_{role}", color)
    obj.data.materials.append(material)
    return obj


def _ellipse(
    name: str,
    collection: bpy.types.Collection,
    role: str,
    view_id: str,
    width: float,
    height: float,
    color: tuple[float, float, float, float],
    location: tuple[float, float, float],
    segments: int = 40,
) -> bpy.types.Object:
    vertices = [(0.0, 0.0, 0.0)]
    vertices.extend(
        (math.cos(i * math.tau / segments) * width / 2.0, 0.0, math.sin(i * math.tau / segments) * height / 2.0)
        for i in range(segments)
    )
    faces = [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)]
    return _mesh_object(name, vertices, faces, collection, role, view_id, color, location)


def _grid(
    name: str,
    collection: bpy.types.Collection,
    role: str,
    view_id: str,
    cols: int,
    rows: int,
    width: float,
    height: float,
    color: tuple[float, float, float, float],
    location: tuple[float, float, float],
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    for row in range(rows):
        z = -height / 2.0 + height * row / max(1, rows - 1)
        for col in range(cols):
            x = -width / 2.0 + width * col / max(1, cols - 1)
            vertices.append((x, 0.0, z))
    faces: list[tuple[int, ...]] = []
    for row in range(rows - 1):
        for col in range(cols - 1):
            a = row * cols + col
            faces.append((a, a + 1, a + cols + 1, a + cols))
    return _mesh_object(name, vertices, faces, collection, role, view_id, color, location)


def _shape_key(obj: bpy.types.Object, name: str, transform) -> None:
    if getattr(obj.data, "shape_keys", None) is None:
        obj.shape_key_add(name="Basis")
    # Blender can create the next key from the currently mixed result. Always
    # start from Basis so authoring shapes remain independent and initially off.
    for existing in obj.data.shape_keys.key_blocks[1:]:
        existing.value = 0.0
    obj.active_shape_key_index = 0
    key = obj.shape_key_add(name=name, from_mix=False)
    key.value = 0.0
    for point in key.data:
        x, y, z = point.co
        nx, ny, nz = transform(float(x), float(y), float(z))
        point.co = (nx, ny, nz)


def _add_eye_shapes(obj: bpy.types.Object) -> None:
    _shape_key(obj, "Blink", lambda x, y, z: (x, y, z * 0.06))
    _shape_key(obj, "Wide", lambda x, y, z: (x, y, z * 1.28))
    _shape_key(obj, "Squint", lambda x, y, z: (x, y, z * 0.48 + abs(x) * 0.035))


def _round_grid(obj: bpy.types.Object, width: float) -> None:
    """Pull the vertical grid edges into a compact eye/mouth oval."""

    half = max(0.001, width / 2.0)
    for point in obj.data.vertices:
        normalized = min(1.0, abs(point.co.x) / half)
        point.co.z *= math.sqrt(max(0.0, 1.0 - normalized * normalized))
    obj.data.update()


def _add_brow_shapes(obj: bpy.types.Object, side: float) -> None:
    _shape_key(obj, "Up", lambda x, y, z: (x, y, z + 0.22))
    _shape_key(obj, "Down", lambda x, y, z: (x, y, z - 0.18))
    _shape_key(obj, "InnerUp", lambda x, y, z: (x, y, z + max(0.0, 1.0 - side * x * 2.0) * 0.22))
    _shape_key(obj, "Angry", lambda x, y, z: (x, y, z - side * x * 0.32))


def _add_mouth_shapes(obj: bpy.types.Object, width: float, height: float) -> None:
    _shape_key(obj, "Open", lambda x, y, z: (x, y, z * 2.3 - (0.18 if z < 0 else 0.0)))
    _shape_key(obj, "Wide", lambda x, y, z: (x * 1.25, y, z * 0.82))
    _shape_key(obj, "Narrow", lambda x, y, z: (x * 0.68, y, z * 1.15))
    _shape_key(obj, "Smile", lambda x, y, z: (x, y, z + (abs(x) / max(0.01, width / 2.0)) ** 2 * 0.22))
    _shape_key(obj, "Frown", lambda x, y, z: (x, y, z - (abs(x) / max(0.01, width / 2.0)) ** 2 * 0.18))


def _make_source_texture(path: Path, pack: str, view_index: int, size: int = 128) -> None:
    """Write a compact, non-destructive source PNG for runtime build tests."""

    path.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new(f"PNE_SOURCE_{view_index}_{pack}", width=size, height=size, alpha=True)
    hue_shift = view_index * 0.035
    pixels: list[float] = []
    for y in range(size):
        for x in range(size):
            nx = (x + 0.5) / size * 2.0 - 1.0
            ny = (y + 0.5) / size * 2.0 - 1.0
            if pack == "base":
                inside = nx * nx / 0.72 + ny * ny / 0.92 <= 1.0
                rgba = (0.88 + hue_shift, 0.61, 0.48 - hue_shift, 1.0 if inside else 0.0)
            elif pack == "face_parts":
                eye = ((nx + 0.42) / 0.22) ** 2 + ((ny - 0.22) / 0.11) ** 2 < 1.0 or ((nx - 0.42) / 0.22) ** 2 + ((ny - 0.22) / 0.11) ** 2 < 1.0
                mouth = abs(ny + 0.38) < 0.045 and abs(nx) < 0.38
                rgba = (0.16, 0.12, 0.16, 1.0 if eye or mouth else 0.0)
            elif pack == "occlusion":
                inside = ny > 0.15 + 0.16 * math.sin((nx + 1.0) * math.pi * 2.0)
                rgba = (0.16 + hue_shift, 0.075, 0.11, 1.0 if inside else 0.0)
            else:
                inside = nx * nx / 0.62 + ((ny + 0.3) / 0.5) ** 2 <= 1.0
                rgba = (0.77 + hue_shift, 0.45, 0.38, 1.0 if inside else 0.0)
            pixels.extend(rgba)
    image.pixels.foreach_set(pixels)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _build_view(collection: bpy.types.Collection, view_id: str, yaw: float, index: int) -> None:
    progress = abs(yaw) / 90.0
    direction = -1.0 if yaw < 0 else 1.0
    face_width = 4.35 - 1.15 * progress
    face_height = 5.35 - 0.18 * progress
    face_x = direction * 0.32 * progress
    skin = (0.88 + index * 0.012, 0.57 - index * 0.015, 0.46, 1.0)
    dark = (0.105, 0.065, 0.095, 1.0)
    mouth_color = (0.56, 0.11, 0.18, 1.0)
    hair = (0.17 + index * 0.018, 0.055, 0.095, 1.0)

    _ellipse(f"BASE_{view_id}", collection, "base", view_id, face_width, face_height, skin, (face_x, 0.0, 0.0))
    jaw = _ellipse(
        f"JAW_MASK_{view_id}",
        collection,
        "jaw",
        view_id,
        face_width * 0.73,
        face_height * 0.42,
        (skin[0] * 0.94, skin[1] * 0.93, skin[2] * 0.93, 1.0),
        (face_x + direction * 0.13 * progress, -0.001, -1.47),
        28,
    )
    _shape_key(jaw, "JawDown", lambda x, y, z: (x, y, z - 0.32 - 0.08 * abs(x)))

    near_x = face_x + direction * (0.92 - 0.56 * progress)
    far_x = face_x - direction * (0.92 - 0.42 * progress)
    near_scale = 1.0 - 0.12 * progress
    far_scale = max(0.16, 1.0 - 0.84 * progress)
    for role, x, scale, side in (
        ("eye_l", -direction * near_x if yaw < 0 else far_x, far_scale if yaw >= 0 else near_scale, -1.0),
        ("eye_r", near_x if yaw >= 0 else -far_x, near_scale if yaw >= 0 else far_scale, 1.0),
    ):
        eye_width = 1.15 * scale
        eye = _grid(f"{role.upper()}_{view_id}", collection, role, view_id, 4, 4, eye_width, 0.56, dark, (x, -0.002, 0.62))
        _round_grid(eye, eye_width)
        _add_eye_shapes(eye)
        brow = _grid(
            f"BROW_{'L' if role == 'eye_l' else 'R'}_{view_id}",
            collection,
            "brow_l" if role == "eye_l" else "brow_r",
            view_id,
            4,
            2,
            1.25 * scale,
            0.14,
            hair,
            (x, -0.0022, 1.37),
        )
        _add_brow_shapes(brow, side)

    mouth_width = 1.48 - 0.45 * progress
    mouth = _grid(
        f"MOUTH_{view_id}", collection, "mouth", view_id, 6, 4, mouth_width, 0.32, mouth_color, (face_x + direction * 0.25 * progress, -0.0023, -0.92)
    )
    _round_grid(mouth, mouth_width)
    _add_mouth_shapes(mouth, mouth_width, 0.32)

    hair_vertices = [
        (-face_width * 0.55, 0.0, 0.9),
        (-face_width * 0.50, 0.0, 2.25),
        (-face_width * 0.20, 0.0, 2.82),
        (face_width * 0.24, 0.0, 2.75),
        (face_width * 0.53, 0.0, 2.18),
        (face_width * 0.48, 0.0, 1.12),
        (face_width * 0.18, 0.0, 1.45),
        (-face_width * 0.02, 0.0, 1.08),
        (-face_width * 0.24, 0.0, 1.48),
    ]
    # Use an explicit interior fan so Blender never has to triangulate the
    # deliberately concave fringe as one large n-gon.
    hair_boundary = hair_vertices
    hair_vertices = [(0.0, 0.0, 1.82), *hair_boundary]
    hair_faces = [(0, index + 1, (index + 1) % len(hair_boundary) + 1) for index in range(len(hair_boundary))]
    _mesh_object(
        f"OCCLUSION_{view_id}",
        hair_vertices,
        hair_faces,
        collection,
        "occlusion",
        view_id,
        hair,
        (face_x, -0.003, 0.0),
    )


def _ensure_camera(scene: bpy.types.Scene) -> None:
    camera_obj = bpy.data.objects.get("PNE_Camera")
    if camera_obj is None:
        camera_data = bpy.data.cameras.new("PNE_Camera")
        camera_obj = bpy.data.objects.new("PNE_Camera", camera_data)
        scene.collection.objects.link(camera_obj)
    camera_obj.location = (0.0, -12.0, 0.0)
    camera_obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    camera_obj.data.type = "ORTHO"
    camera_obj.data.ortho_scale = 7.2
    scene.camera = camera_obj


def _hide_factory_defaults(scene: bpy.types.Scene) -> None:
    """Keep Blender's untouched starter cube/light out of the sample preview."""

    candidates = [obj for obj in scene.objects if not obj.get("pne_sample") and obj.name != "PNE_Camera"]
    if {obj.name for obj in candidates}.issubset({"Cube", "Camera", "Light"}):
        for name in ("Cube", "Light"):
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_set(True)
                obj.hide_render = True


def build_sample(scene: bpy.types.Scene) -> tuple[int, Path]:
    """Create the fixed v0.1 four-view sample and its source texture packs."""

    clear_sample()
    settings = scene.pne_settings
    settings.views.clear()
    settings.validation_issues.clear()
    settings.character_id = "pne_sample"
    _hide_factory_defaults(scene)

    master = bpy.data.collections.new(MASTER_COLLECTION)
    scene.collection.children.link(master)
    master["pne_character_id"] = settings.character_id
    master["pne_schema_version"] = "0.1"

    # An unsaved .blend has no meaningful // root. Keep that first-run sample in
    # Blender's writable temp directory; once the file is saved, //pne_source is
    # stable and travels with the project.
    project_root = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(bpy.app.tempdir)
    source_root = project_root / "pne_source" / settings.character_id
    for index, (view_id, yaw) in enumerate(SAMPLE_VIEWS):
        collection = _new_collection(f"STATE_{view_id}", master)
        collection["pne_view_id"] = view_id
        collection["yaw_deg"] = yaw
        collection["pitch_deg"] = 0.0
        _build_view(collection, view_id, yaw, index)

        state = settings.views.add()
        state.view_id = view_id
        state.yaw_deg = yaw
        state.pitch_deg = 0.0
        state.collection_name = collection.name
        pack_paths: dict[str, str] = {}
        for pack in ("base", "face_parts", "occlusion", "jaw"):
            path = source_root / view_id / f"{pack}.png"
            _make_source_texture(path, pack, index)
            pack_paths[pack] = str(path)
        state.base_texture = pack_paths["base"]
        state.face_parts_texture = pack_paths["face_parts"]
        state.occlusion_texture = pack_paths["occlusion"]
        state.jaw_texture = pack_paths["jaw"]
        state.estimated_memory_mb = 21.25
        for obj in collection.all_objects:
            pack = str(obj.get("pne_texture_pack", ""))
            if pack in pack_paths:
                obj["pne_texture_path"] = pack_paths[pack]

    _ensure_camera(scene)
    settings.yaw_deg = 0.0
    settings.pitch_deg = 0.0
    settings.transition_mode = "DITHER"
    settings.interpolation = "SMOOTHSTEP"
    settings.validation_summary = "Not validated"
    from .runtime import update_preview

    update_preview(scene)
    return len(settings.views), source_root
