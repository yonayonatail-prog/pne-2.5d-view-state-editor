"""Material helpers for complementary view-state dithering."""

from __future__ import annotations

from typing import Iterable

import bpy


def _set_transparency(material: bpy.types.Material) -> None:
    material.use_nodes = True
    material.use_backface_culling = False
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
        except (TypeError, ValueError):
            try:
                material.surface_render_method = "BLENDED"
            except (TypeError, ValueError):
                pass
    elif hasattr(material, "blend_method"):
        try:
            material.blend_method = "HASHED"
            material.shadow_method = "NONE"
        except (TypeError, ValueError):
            pass


def create_dither_material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    image: bpy.types.Image | None = None,
) -> bpy.types.Material:
    """Create an unlit material with driven alpha and a stochastic pixel mask."""

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _set_transparency(material)
    material.diffuse_color = color
    material["pne_material"] = True

    tree = material.node_tree
    tree.nodes.clear()
    nodes = tree.nodes
    links = tree.links

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "PNE_OUTPUT"
    output.location = (760, 80)
    emission = nodes.new("ShaderNodeEmission")
    emission.name = "PNE_EMISSION"
    emission.location = (500, 170)
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (500, -40)
    mix_shader = nodes.new("ShaderNodeMixShader")
    mix_shader.name = "PNE_SURFACE_MIX"
    mix_shader.location = (650, 80)

    if image is not None:
        texture = nodes.new("ShaderNodeTexImage")
        texture.name = "PNE_TEXTURE"
        texture.image = image
        texture.interpolation = "Linear"
        texture.extension = "CLIP"
        texture.location = (-650, 230)
        links.new(texture.outputs["Color"], emission.inputs["Color"])
        source_alpha = texture.outputs["Alpha"]
    else:
        emission.inputs["Color"].default_value = color
        base_alpha = nodes.new("ShaderNodeValue")
        base_alpha.name = "PNE_BASE_ALPHA"
        base_alpha.outputs[0].default_value = color[3]
        source_alpha = base_alpha.outputs[0]

    texture_coord = nodes.new("ShaderNodeTexCoord")
    texture_coord.location = (-690, -180)
    pixel_scale = nodes.new("ShaderNodeVectorMath")
    pixel_scale.operation = "SCALE"
    pixel_scale.inputs[3].default_value = 96.0
    pixel_scale.location = (-500, -180)
    pixel_floor = nodes.new("ShaderNodeVectorMath")
    pixel_floor.operation = "FLOOR"
    pixel_floor.location = (-320, -180)
    white_noise = nodes.new("ShaderNodeTexWhiteNoise")
    white_noise.noise_dimensions = "3D"
    white_noise.location = (-135, -180)
    links.new(texture_coord.outputs["Generated"], pixel_scale.inputs[0])
    links.new(pixel_scale.outputs[0], pixel_floor.inputs[0])
    links.new(pixel_floor.outputs[0], white_noise.inputs["Vector"])

    threshold = nodes.new("ShaderNodeValue")
    threshold.name = "PNE_THRESHOLD"
    threshold.label = "Transition blend"
    threshold.outputs[0].default_value = 0.0
    threshold.location = (-140, -340)
    slot = nodes.new("ShaderNodeValue")
    slot.name = "PNE_SLOT"
    slot.label = "0=A, 1=B"
    slot.outputs[0].default_value = 0.0
    slot.location = (-140, -410)

    compare_a = nodes.new("ShaderNodeMath")
    compare_a.operation = "GREATER_THAN"
    compare_a.location = (45, -190)
    compare_b = nodes.new("ShaderNodeMath")
    compare_b.operation = "LESS_THAN"
    compare_b.location = (45, -270)
    links.new(white_noise.outputs["Value"], compare_a.inputs[0])
    links.new(threshold.outputs[0], compare_a.inputs[1])
    links.new(white_noise.outputs["Value"], compare_b.inputs[0])
    links.new(threshold.outputs[0], compare_b.inputs[1])

    invert_slot = nodes.new("ShaderNodeMath")
    invert_slot.operation = "SUBTRACT"
    invert_slot.inputs[0].default_value = 1.0
    invert_slot.location = (40, -420)
    links.new(slot.outputs[0], invert_slot.inputs[1])
    a_weight = nodes.new("ShaderNodeMath")
    a_weight.operation = "MULTIPLY"
    a_weight.location = (225, -190)
    b_weight = nodes.new("ShaderNodeMath")
    b_weight.operation = "MULTIPLY"
    b_weight.location = (225, -270)
    links.new(compare_a.outputs[0], a_weight.inputs[0])
    links.new(invert_slot.outputs[0], a_weight.inputs[1])
    links.new(compare_b.outputs[0], b_weight.inputs[0])
    links.new(slot.outputs[0], b_weight.inputs[1])
    dither_sum = nodes.new("ShaderNodeMath")
    dither_sum.operation = "ADD"
    dither_sum.location = (395, -220)
    links.new(a_weight.outputs[0], dither_sum.inputs[0])
    links.new(b_weight.outputs[0], dither_sum.inputs[1])

    opacity = nodes.new("ShaderNodeValue")
    opacity.name = "PNE_OPACITY"
    opacity.label = "Non-dither opacity"
    opacity.outputs[0].default_value = 1.0
    opacity.location = (45, -510)
    use_dither = nodes.new("ShaderNodeValue")
    use_dither.name = "PNE_USE_DITHER"
    use_dither.outputs[0].default_value = 1.0
    use_dither.location = (45, -570)
    mix_mask = nodes.new("ShaderNodeMix")
    mix_mask.data_type = "FLOAT"
    mix_mask.name = "PNE_MASK_MODE"
    mix_mask.location = (395, -390)
    links.new(use_dither.outputs[0], mix_mask.inputs[0])
    links.new(opacity.outputs[0], mix_mask.inputs[2])
    links.new(dither_sum.outputs[0], mix_mask.inputs[3])

    final_alpha = nodes.new("ShaderNodeMath")
    final_alpha.operation = "MULTIPLY"
    final_alpha.location = (500, -250)
    links.new(source_alpha, final_alpha.inputs[0])
    links.new(mix_mask.outputs[2], final_alpha.inputs[1])
    links.new(final_alpha.outputs[0], mix_shader.inputs[0])
    links.new(transparent.outputs[0], mix_shader.inputs[1])
    links.new(emission.outputs[0], mix_shader.inputs[2])
    links.new(mix_shader.outputs[0], output.inputs["Surface"])
    return material


def iter_pne_materials(objects: Iterable[bpy.types.Object]) -> Iterable[bpy.types.Material]:
    seen: set[int] = set()
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.get("pne_material"):
                continue
            pointer = material.as_pointer()
            if pointer not in seen:
                seen.add(pointer)
                yield material


def set_material_transition(material: bpy.types.Material, slot: int, blend: float, mode: str, opacity: float) -> None:
    if not material.use_nodes:
        return
    nodes = material.node_tree.nodes
    if nodes.get("PNE_SLOT"):
        nodes["PNE_SLOT"].outputs[0].default_value = float(slot)
    if nodes.get("PNE_THRESHOLD"):
        nodes["PNE_THRESHOLD"].outputs[0].default_value = float(blend)
    if nodes.get("PNE_OPACITY"):
        nodes["PNE_OPACITY"].outputs[0].default_value = float(opacity)
    if nodes.get("PNE_USE_DITHER"):
        nodes["PNE_USE_DITHER"].outputs[0].default_value = 1.0 if mode in {"DITHER", "WARP_DITHER"} else 0.0
