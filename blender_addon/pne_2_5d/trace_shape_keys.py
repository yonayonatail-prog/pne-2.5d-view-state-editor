"""Native image trace to normalized ribbon meshes and Shape Keys.

The tracer intentionally treats raster/SVG contours as guides.  It always
rebuilds a role-specific mesh so Basis and target Shape Keys share identical
topology.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import bpy
import numpy as np

from .constants import ROLE_CONCEPT_Z, ROLE_RENDER_ORDER, ROLE_TEXTURE_PACK
from .materials import create_dither_material


TRACE_LOG_NAME = "PNE_TRACE_LOG"
TRACE_PREVIEW_COLLECTION = "PNE_TRACE_PREVIEW"


class TraceError(RuntimeError):
    """A user-correctable failure in the trace pipeline."""


@dataclass(frozen=True)
class ImageTrace:
    path: Path
    width: int
    height: int
    source_points: int
    island_count: int
    removed_islands: int
    stations: np.ndarray
    half_widths: np.ndarray


@dataclass(frozen=True)
class TraceBuildData:
    basis: ImageTrace
    target: ImageTrace
    half: ImageTrace | None
    basis_centers: np.ndarray
    target_centers: np.ndarray
    half_centers: np.ndarray | None
    basis_vertices: np.ndarray
    target_vertices: np.ndarray
    half_vertices: np.ndarray | None
    faces: tuple[tuple[int, int, int, int], ...]
    endpoint_error: float


def _resolved_path(raw_path: str) -> Path:
    path = Path(bpy.path.abspath(raw_path)).resolve()
    if not path.is_file():
        raise TraceError(f"Source image does not exist: {raw_path or '<empty>'}")
    return path


def _image_pixels(path: Path) -> tuple[np.ndarray, int, int]:
    try:
        image = bpy.data.images.load(str(path), check_existing=True)
    except RuntimeError as exc:
        raise TraceError(f"Cannot load image {path.name}: {exc}") from exc
    width, height = int(image.size[0]), int(image.size[1])
    if width <= 0 or height <= 0:
        raise TraceError(f"Image has invalid dimensions: {path.name}")
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    return pixels.reshape((height, width, 4)), width, height


def _build_mask(rgba: np.ndarray, mode: str, threshold: float) -> np.ndarray:
    threshold = float(np.clip(threshold, 0.001, 0.999))
    alpha = rgba[:, :, 3]
    luminance = rgba[:, :, 0] * 0.2126 + rgba[:, :, 1] * 0.7152 + rgba[:, :, 2] * 0.0722
    darkness = 1.0 - luminance
    if mode == "ALPHA":
        signal = alpha
    elif mode == "THRESHOLD":
        # Alpha keeps transparent black RGB from becoming foreground.
        signal = darkness * np.maximum(alpha, 0.001)
    elif mode == "EDGE":
        source = np.maximum(alpha, darkness * alpha)
        grad_y, grad_x = np.gradient(source)
        signal = np.sqrt(grad_x * grad_x + grad_y * grad_y)
        maximum = float(signal.max())
        if maximum > 0.0:
            signal /= maximum
    else:
        raise TraceError(f"Unknown trace mode: {mode}")
    mask = signal >= threshold
    if not np.any(mask):
        raise TraceError("Trace mask is empty; lower Threshold or change Trace Mode")
    return mask


def _connected_components(mask: np.ndarray, min_area: int) -> list[np.ndarray]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.bool_)
    components: list[np.ndarray] = []
    foreground = np.argwhere(mask)
    for y_value, x_value in foreground:
        y, x = int(y_value), int(x_value)
        if visited[y, x]:
            continue
        queue: deque[tuple[int, int]] = deque([(y, x)])
        visited[y, x] = True
        points: list[tuple[float, float]] = []
        while queue:
            current_y, current_x = queue.popleft()
            points.append((float(current_x), float(current_y)))
            for offset_y in (-1, 0, 1):
                for offset_x in (-1, 0, 1):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    next_x = current_x + offset_x
                    next_y = current_y + offset_y
                    if 0 <= next_x < width and 0 <= next_y < height and mask[next_y, next_x] and not visited[next_y, next_x]:
                        visited[next_y, next_x] = True
                        queue.append((next_y, next_x))
        if len(points) >= min_area:
            components.append(np.asarray(points, dtype=np.float64))
    components.sort(key=len, reverse=True)
    if not components:
        raise TraceError(f"No connected island reaches Min Area ({min_area}px)")
    return components


def _smooth_series(values: np.ndarray, strength: float) -> np.ndarray:
    passes = int(round(float(np.clip(strength, 0.0, 1.0)) * 4.0))
    result = values.astype(np.float64, copy=True)
    for _ in range(passes):
        if len(result) <= 2:
            break
        previous = result.copy()
        result[1:-1] = previous[:-2] * 0.25 + previous[1:-1] * 0.5 + previous[2:] * 0.25
    return result


def _resample_path(points: np.ndarray, widths: np.ndarray, station_count: int) -> tuple[np.ndarray, np.ndarray]:
    if len(points) < 2:
        raise TraceError("Guide path has fewer than two points")
    distances = np.linalg.norm(np.diff(points, axis=0), axis=1)
    keep = np.concatenate(([True], distances > 1e-6))
    points = points[keep]
    widths = widths[keep]
    if len(points) < 2:
        raise TraceError("Guide path collapsed to a single point")
    cumulative = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))))
    total = float(cumulative[-1])
    if total <= 1e-6:
        raise TraceError("Guide path has zero length")
    targets = np.linspace(0.0, total, station_count)
    sampled = np.column_stack(
        (
            np.interp(targets, cumulative, points[:, 0]),
            np.interp(targets, cumulative, points[:, 1]),
        )
    )
    sampled_widths = np.interp(targets, cumulative, widths)
    return sampled, sampled_widths


def _extract_centerline(component: np.ndarray, station_count: int, smooth: float) -> tuple[np.ndarray, np.ndarray, int]:
    center = component.mean(axis=0)
    centered = component - center
    covariance = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    if axis[0] < 0.0 or (abs(axis[0]) < 1e-8 and axis[1] < 0.0):
        axis = -axis
    normal = np.asarray((-axis[1], axis[0]), dtype=np.float64)
    along = centered @ axis
    across = centered @ normal
    low, high = float(along.min()), float(along.max())
    if high - low < 2.0:
        raise TraceError("Detected island is too short for an open guide path")

    bin_count = max(64, station_count * 4)
    edges = np.linspace(low, high, bin_count + 1)
    guide: list[np.ndarray] = []
    half_widths: list[float] = []
    for index in range(bin_count):
        if index == bin_count - 1:
            selected = (along >= edges[index]) & (along <= edges[index + 1])
        else:
            selected = (along >= edges[index]) & (along < edges[index + 1])
        if not np.any(selected):
            continue
        along_value = float(np.median(along[selected]))
        across_values = across[selected]
        across_value = float(np.median(across_values))
        lower = float(np.percentile(across_values, 5.0))
        upper = float(np.percentile(across_values, 95.0))
        guide.append(center + axis * along_value + normal * across_value)
        half_widths.append(max(0.75, (upper - lower + 1.0) * 0.5))

    if len(guide) < 4:
        raise TraceError("Could not derive a stable centerline; use a lower Threshold")
    guide_array = np.asarray(guide, dtype=np.float64)
    widths_array = np.asarray(half_widths, dtype=np.float64)
    guide_array[:, 0] = _smooth_series(guide_array[:, 0], smooth)
    guide_array[:, 1] = _smooth_series(guide_array[:, 1], smooth)
    widths_array = _smooth_series(widths_array, smooth)
    sampled, sampled_widths = _resample_path(guide_array, widths_array, station_count)
    return sampled, sampled_widths, len(guide)


def trace_image(
    raw_path: str,
    *,
    mode: str,
    threshold: float,
    min_area: int,
    smooth: float,
    station_count: int,
) -> ImageTrace:
    path = _resolved_path(raw_path)
    rgba, width, height = _image_pixels(path)
    mask = _build_mask(rgba, mode, threshold)
    components = _connected_components(mask, max(1, int(min_area)))
    stations, half_widths, source_points = _extract_centerline(components[0], station_count, smooth)
    return ImageTrace(
        path=path,
        width=width,
        height=height,
        source_points=source_points,
        island_count=len(components),
        removed_islands=max(0, len(components) - 1),
        stations=stations,
        half_widths=half_widths,
    )


def _similarity_to_basis(basis: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
    basis_vector = basis[-1] - basis[0]
    target_vector = target[-1] - target[0]
    basis_length = float(np.linalg.norm(basis_vector))
    target_length = float(np.linalg.norm(target_vector))
    if basis_length <= 1e-6 or target_length <= 1e-6:
        raise TraceError("Inner/outer corner distance is too small")
    if float(np.dot(basis_vector, target_vector)) < 0.0:
        target = target[::-1].copy()
        target_vector = target[-1] - target[0]
    basis_angle = math.atan2(float(basis_vector[1]), float(basis_vector[0]))
    target_angle = math.atan2(float(target_vector[1]), float(target_vector[0]))
    angle = basis_angle - target_angle
    cosine, sine = math.cos(angle), math.sin(angle)
    rotation = np.asarray(((cosine, -sine), (sine, cosine)), dtype=np.float64)
    scale = basis_length / target_length
    basis_mid = (basis[0] + basis[-1]) * 0.5
    target_mid = (target[0] + target[-1]) * 0.5
    aligned = (target - target_mid) @ rotation.T * scale + basis_mid
    aligned[0] = basis[0]
    aligned[-1] = basis[-1]
    return aligned, scale


def _to_world_pair(
    basis: ImageTrace,
    target: ImageTrace,
    half: ImageTrace | None,
    *,
    mesh_width: float,
    reverse_path: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray, np.ndarray, np.ndarray | None, float]:
    basis_points = basis.stations.copy()
    basis_widths = basis.half_widths.copy()
    target_points = target.stations.copy()
    target_widths = target.half_widths.copy()
    if reverse_path:
        basis_points = basis_points[::-1].copy()
        basis_widths = basis_widths[::-1].copy()
        target_points = target_points[::-1].copy()
        target_widths = target_widths[::-1].copy()

    target_aligned, target_scale = _similarity_to_basis(basis_points, target_points)
    basis_vector = basis_points[-1] - basis_points[0]
    source_length = float(np.linalg.norm(basis_vector))
    world_scale = max(0.01, float(mesh_width)) / source_length
    origin = (basis_points[0] + basis_points[-1]) * 0.5
    basis_world = (basis_points - origin) * world_scale
    target_world = (target_aligned - origin) * world_scale
    basis_width_world = basis_widths * world_scale
    target_width_world = target_widths * target_scale * world_scale

    half_world: np.ndarray | None = None
    half_width_world: np.ndarray | None = None
    if half is not None:
        half_points = half.stations[::-1].copy() if reverse_path else half.stations.copy()
        half_widths = half.half_widths[::-1].copy() if reverse_path else half.half_widths.copy()
        half_aligned, half_scale = _similarity_to_basis(basis_points, half_points)
        half_world = (half_aligned - origin) * world_scale
        half_width_world = half_widths * half_scale * world_scale

    minimum_width = max(0.002, mesh_width * 0.004)
    maximum_width = mesh_width * 0.18
    basis_width_world = np.clip(basis_width_world, minimum_width, maximum_width)
    target_width_world = np.clip(target_width_world, minimum_width, maximum_width)
    if half_width_world is not None:
        half_width_world = np.clip(half_width_world, minimum_width, maximum_width)
    endpoint_error = float(
        max(
            np.linalg.norm(target_world[0] - basis_world[0]),
            np.linalg.norm(target_world[-1] - basis_world[-1]),
        )
    )
    return (
        basis_world,
        target_world,
        half_world,
        basis_width_world,
        target_width_world,
        half_width_world,
        endpoint_error,
    )


def _ribbon_vertices(centers: np.ndarray, half_widths: np.ndarray) -> np.ndarray:
    vertices: list[tuple[float, float, float]] = []
    count = len(centers)
    for index, center in enumerate(centers):
        if index == 0:
            tangent = centers[1] - center
        elif index == count - 1:
            tangent = center - centers[index - 1]
        else:
            tangent = centers[index + 1] - centers[index - 1]
        length = float(np.linalg.norm(tangent))
        if length <= 1e-8:
            tangent = np.asarray((1.0, 0.0), dtype=np.float64)
        else:
            tangent = tangent / length
        normal = np.asarray((-tangent[1], tangent[0]), dtype=np.float64)
        offset = normal * float(half_widths[index])
        top = center + offset
        bottom = center - offset
        vertices.append((float(top[0]), 0.0, float(top[1])))
        vertices.append((float(bottom[0]), 0.0, float(bottom[1])))
    return np.asarray(vertices, dtype=np.float64)


def build_trace_data(settings) -> TraceBuildData:
    station_count = max(4, int(settings.trace_stations))
    common = {
        "mode": settings.trace_mode,
        "threshold": settings.trace_threshold,
        "min_area": settings.trace_min_area,
        "smooth": settings.trace_smooth,
        "station_count": station_count,
    }
    basis = trace_image(settings.trace_basis_image, **common)
    target = trace_image(settings.trace_target_image, **common)
    half = trace_image(settings.trace_half_image, **common) if settings.trace_half_image.strip() else None
    (
        basis_centers,
        target_centers,
        half_centers,
        basis_widths,
        target_widths,
        half_widths,
        endpoint_error,
    ) = _to_world_pair(
        basis,
        target,
        half,
        mesh_width=settings.trace_mesh_width,
        reverse_path=settings.trace_reverse_path,
    )
    basis_vertices = _ribbon_vertices(basis_centers, basis_widths)
    target_vertices = _ribbon_vertices(target_centers, target_widths)
    half_vertices = _ribbon_vertices(half_centers, half_widths) if half_centers is not None and half_widths is not None else None
    faces = tuple((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(station_count - 1))
    return TraceBuildData(
        basis=basis,
        target=target,
        half=half,
        basis_centers=basis_centers,
        target_centers=target_centers,
        half_centers=half_centers,
        basis_vertices=basis_vertices,
        target_vertices=target_vertices,
        half_vertices=half_vertices,
        faces=faces,
        endpoint_error=endpoint_error,
    )


def _ensure_preview_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    collection = bpy.data.collections.get(TRACE_PREVIEW_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(TRACE_PREVIEW_COLLECTION)
        scene.collection.children.link(collection)
    return collection


def clear_trace_preview(scene: bpy.types.Scene) -> None:
    collection = bpy.data.collections.get(TRACE_PREVIEW_COLLECTION)
    if collection is None:
        return
    for obj in list(collection.objects):
        if obj.get("pne_trace_preview") or obj.get("pne_trace_output"):
            bpy.data.objects.remove(obj, do_unlink=True)
    if not collection.objects and collection.name in bpy.data.collections:
        bpy.data.collections.remove(collection)


def _new_curve(name: str, points: np.ndarray, color: tuple[float, float, float, float], collection: bpy.types.Collection) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.008
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for index, point in enumerate(points):
        spline.points[index].co = (float(point[0]), -0.03, float(point[1]), 1.0)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    material = create_dither_material(f"MAT_{name}", color)
    curve.materials.append(material)
    obj["pne_trace_preview"] = True
    return obj


def create_path_preview(scene: bpy.types.Scene, data: TraceBuildData) -> tuple[bpy.types.Object, ...]:
    clear_trace_preview(scene)
    collection = _ensure_preview_collection(scene)
    objects = [
        _new_curve("trace_basis_path", data.basis_centers, (0.05, 0.8, 0.2, 1.0), collection),
        _new_curve("trace_target_path", data.target_centers, (0.9, 0.08, 0.65, 1.0), collection),
    ]
    if data.half_centers is not None:
        objects.append(_new_curve("trace_half_path", data.half_centers, (0.95, 0.65, 0.05, 1.0), collection))
    return tuple(objects)


def _role_metadata(settings) -> tuple[str, str, str]:
    side = settings.trace_side.lower()
    if settings.trace_role == "UPPER_EYELID":
        if side not in {"left", "right"}:
            raise TraceError("Upper Eyelid requires Left or Right Side")
        suffix = "l" if side == "left" else "r"
        return f"eye_{suffix}", "lid_upper_line", f"blink_{suffix}"
    if settings.trace_role == "BROW":
        if side not in {"left", "right"}:
            raise TraceError("Brow requires Left or Right Side")
        suffix = "l" if side == "left" else "r"
        return f"brow_{suffix}", "brow_line", f"brow_{suffix}"
    if settings.trace_role == "MOUTH_LINE":
        return "mouth", "mouth_line", "mouth_expression"
    return "nose", "nose_line", ""


def create_shape_key_mesh(scene: bpy.types.Scene, settings, data: TraceBuildData) -> bpy.types.Object:
    collection = _ensure_preview_collection(scene)
    role, subrole, channel = _role_metadata(settings)
    name = f"trace_{role}_{subrole}"
    old = bpy.data.objects.get(name)
    if old is not None and old.get("pne_trace_output") and TRACE_PREVIEW_COLLECTION in {item.name for item in old.users_collection}:
        bpy.data.objects.remove(old, do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(value) for value in data.basis_vertices], [], list(data.faces))
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location.y = -0.002

    uv_layer = mesh.uv_layers.new(name="UVMap")
    station_count = len(data.basis_centers)
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            station = vertex_index // 2
            is_top = vertex_index % 2 == 0
            uv_layer.data[loop_index].uv = (station / max(1, station_count - 1), 1.0 if is_top else 0.0)

    obj.shape_key_add(name="Basis", from_mix=False)
    if data.half_vertices is not None:
        half_key = obj.shape_key_add(name="BlinkHalf", from_mix=False)
        for point, coordinate in zip(half_key.data, data.half_vertices):
            point.co = coordinate
    blink_key = obj.shape_key_add(name="Blink", from_mix=False)
    for point, coordinate in zip(blink_key.data, data.target_vertices):
        point.co = coordinate

    material = create_dither_material(f"MAT_{name}", (0.015, 0.008, 0.012, 1.0))
    mesh.materials.append(material)
    topology_source = json.dumps({"stations": station_count, "faces": data.faces}, separators=(",", ":"))
    topology_hash = hashlib.sha256(topology_source.encode("utf-8")).hexdigest()[:16]
    obj["pne_trace_output"] = True
    obj["pne_trace_preview"] = True
    obj["pne_role"] = role
    obj["pne_subrole"] = subrole
    obj["pne_expression_channel"] = channel
    obj["pne_template_id"] = f"eyelid_ribbon_v1_{station_count}" if settings.trace_role == "UPPER_EYELID" else f"ribbon_v1_{station_count}"
    obj["pne_topology_hash"] = topology_hash
    obj["pne_required_shape_keys"] = "BlinkHalf,Blink" if data.half_vertices is not None else "Blink"
    obj["pne_trace_source_basis"] = str(data.basis.path)
    obj["pne_trace_source_key"] = str(data.target.path)
    obj["pne_trace_backend"] = "native_alpha"
    obj["pne_trace_stations"] = station_count
    obj["pne_trace_endpoint_error"] = data.endpoint_error
    obj["pne_uv_padding"] = 32
    settings.trace_output_object = obj.name
    set_trace_blink_value(scene, settings.trace_blink_preview)
    return obj


def set_trace_blink_value(scene: bpy.types.Scene, value: float) -> None:
    value = float(np.clip(value, 0.0, 1.0))
    for obj in scene.objects:
        if not obj.get("pne_trace_output") or not getattr(obj.data, "shape_keys", None):
            continue
        keys = obj.data.shape_keys.key_blocks
        blink = keys.get("Blink")
        half = keys.get("BlinkHalf")
        if half is None:
            if blink is not None:
                blink.value = value
        elif value < 0.5:
            half.value = value * 2.0
            if blink is not None:
                blink.value = 0.0
        else:
            half.value = (1.0 - value) * 2.0
            if blink is not None:
                blink.value = value * 2.0 - 1.0


def assign_to_current_view(scene: bpy.types.Scene, settings, obj: bpy.types.Object) -> tuple[str, str]:
    if not settings.views:
        raise TraceError("No View State exists; build or add a View first")
    index = min(settings.active_view_index, len(settings.views) - 1)
    state = settings.views[index]
    target_collection = bpy.data.collections.get(state.collection_name)
    if target_collection is None:
        raise TraceError(f"Current View collection does not exist: {state.collection_name}")
    role = str(obj.get("pne_role", ""))
    subrole = str(obj.get("pne_subrole", "part"))
    pne_id = f"{role}_{subrole}.{state.view_id}"
    for candidate in scene.objects:
        if candidate != obj and candidate.get("pne_id") == pne_id:
            raise TraceError(f"Current View already contains {pne_id}")
    if target_collection not in obj.users_collection:
        target_collection.objects.link(obj)
    for collection in list(obj.users_collection):
        if collection != target_collection:
            collection.objects.unlink(obj)
    stable_name = f"{role}_{subrole}_{state.view_id}"
    obj.name = stable_name
    obj.data.name = stable_name
    obj["pne_id"] = pne_id
    obj["pne_view_id"] = state.view_id
    obj["pne_render_order"] = ROLE_RENDER_ORDER.get(role, 20)
    obj["pne_concept_z"] = ROLE_CONCEPT_Z.get(role, 0.002)
    obj["pne_texture_pack"] = ROLE_TEXTURE_PACK.get(role, "face_parts")
    obj["pne_trace_preview"] = False
    settings.trace_output_object = obj.name
    return state.view_id, pne_id


def trace_log_payload(settings, data: TraceBuildData, *, status: str, object_name: str = "") -> dict[str, object]:
    return {
        "status": status,
        "role": settings.trace_role.lower(),
        "side": settings.trace_side.lower(),
        "basis": str(data.basis.path),
        "target": str(data.target.path),
        "backend": "native_alpha",
        "mode": settings.trace_mode.lower(),
        "threshold": round(float(settings.trace_threshold), 4),
        "basis_islands": data.basis.island_count,
        "target_islands": data.target.island_count,
        "basis_path_points": data.basis.source_points,
        "target_path_points": data.target.source_points,
        "stations": len(data.basis_centers),
        "mesh_vertices": len(data.basis_vertices),
        "mesh_faces": len(data.faces),
        "shape_keys": ["Basis", *(("BlinkHalf",) if data.half is not None else ()), "Blink"],
        "endpoint_error": round(data.endpoint_error, 8),
        "object": object_name,
    }


def append_trace_log(payload: dict[str, object]) -> None:
    text = bpy.data.texts.get(TRACE_LOG_NAME) or bpy.data.texts.new(TRACE_LOG_NAME)
    text.write("[TRACE LOG]\n")
    for key, value in payload.items():
        text.write(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
    text.write("\n")


def append_trace_error(settings, stage: str, error: Exception) -> None:
    text = bpy.data.texts.get(TRACE_LOG_NAME) or bpy.data.texts.new(TRACE_LOG_NAME)
    text.write("[TRACE ERROR]\n")
    text.write(f"role: {settings.trace_role.lower()}\n")
    text.write(f"side: {settings.trace_side.lower()}\n")
    text.write(f"stage: {stage}\n")
    text.write(f"reason: {json.dumps(str(error), ensure_ascii=False)}\n\n")


def iter_trace_objects(scene: bpy.types.Scene) -> Iterable[bpy.types.Object]:
    return (obj for obj in scene.objects if obj.get("pne_trace_output"))
