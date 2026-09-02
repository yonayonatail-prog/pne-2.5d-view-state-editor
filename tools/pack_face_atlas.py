"""Pack face-part PNGs into a deterministic runtime atlas.

The source folder remains authoring-friendly: files can stay separated and
organized in subfolders. The generated atlas stores trimmed rectangles,
source sizes, and source paths so a Blender/Three.js builder can reconstruct
the original part size and pivot without relying on the packed image.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result *= 2
    return result


def sprite_id(relative_path: Path) -> str:
    """Create a stable, collision-resistant ID from a relative source path."""

    return relative_path.with_suffix("").as_posix().replace("/", "_")


def trim_rgba(image: Image.Image, alpha_threshold: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha_threshold > 0:
        alpha = alpha.point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0, 0, 0)
    return rgba.crop(bbox), bbox


def padded_with_extruded_edges(image: Image.Image, padding: int) -> Image.Image:
    if padding <= 0:
        return image

    width, height = image.size
    result = Image.new("RGBA", (width + padding * 2, height + padding * 2))
    result.paste(image, (padding, padding))

    top = image.crop((0, 0, width, 1)).resize((width, padding), Image.Resampling.NEAREST)
    bottom = image.crop((0, height - 1, width, height)).resize((width, padding), Image.Resampling.NEAREST)
    left = image.crop((0, 0, 1, height)).resize((padding, height), Image.Resampling.NEAREST)
    right = image.crop((width - 1, 0, width, height)).resize((padding, height), Image.Resampling.NEAREST)
    result.paste(top, (padding, 0))
    result.paste(bottom, (padding, padding + height))
    result.paste(left, (0, padding))
    result.paste(right, (padding + width, padding))

    corners = {
        (0, 0): image.crop((0, 0, 1, 1)).resize((padding, padding), Image.Resampling.NEAREST),
        (padding + width, 0): image.crop((width - 1, 0, width, 1)).resize((padding, padding), Image.Resampling.NEAREST),
        (0, padding + height): image.crop((0, height - 1, 1, height)).resize((padding, padding), Image.Resampling.NEAREST),
        (padding + width, padding + height): image.crop((width - 1, height - 1, width, height)).resize((padding, padding), Image.Resampling.NEAREST),
    }
    for position, corner in corners.items():
        result.paste(corner, position)
    return result


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def contains(container: tuple[int, int, int, int], child: tuple[int, int, int, int]) -> bool:
    cx, cy, cw, ch = container
    x, y, w, h = child
    return cx <= x and cy <= y and cx + cw >= x + w and cy + ch >= y + h


def prune_free_rectangles(rectangles: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    pruned: list[tuple[int, int, int, int]] = []
    for index, rectangle in enumerate(rectangles):
        if rectangle[2] <= 0 or rectangle[3] <= 0:
            continue
        if any(index != other_index and contains(other, rectangle) for other_index, other in enumerate(rectangles)):
            continue
        pruned.append(rectangle)
    return pruned


def maxrects_pack(items: list[dict], width: int, height: int, padding: int) -> bool:
    """Pack items into a fixed bin using a deterministic MaxRects pass."""

    free_rectangles = [(0, 0, width, height)]
    ordered = sorted(items, key=lambda item: (-(item["image"].width * item["image"].height), item["id"]))
    for item in ordered:
        image_width, image_height = item["image"].size
        packed_width = image_width + padding * 2
        packed_height = image_height + padding * 2
        best_index = None
        best_score = None
        for index, free in enumerate(free_rectangles):
            _, _, free_width, free_height = free
            if packed_width > free_width or packed_height > free_height:
                continue
            leftover_width = free_width - packed_width
            leftover_height = free_height - packed_height
            score = (min(leftover_width, leftover_height), max(leftover_width, leftover_height), free[1], free[0])
            if best_score is None or score < best_score:
                best_score = score
                best_index = index
        if best_index is None:
            return False

        free = free_rectangles[best_index]
        placed = (free[0], free[1], packed_width, packed_height)
        item["packed_x"] = placed[0]
        item["packed_y"] = placed[1]
        item["x"] = placed[0] + padding
        item["y"] = placed[1] + padding
        item["width"] = image_width
        item["height"] = image_height

        split_rectangles: list[tuple[int, int, int, int]] = []
        for free_rectangle in free_rectangles:
            if not intersects(free_rectangle, placed):
                split_rectangles.append(free_rectangle)
                continue
            fx, fy, fw, fh = free_rectangle
            px, py, pw, ph = placed
            if px > fx:
                split_rectangles.append((fx, fy, px - fx, fh))
            if px + pw < fx + fw:
                split_rectangles.append((px + pw, fy, fx + fw - px - pw, fh))
            if py > fy:
                split_rectangles.append((fx, fy, fw, py - fy))
            if py + ph < fy + fh:
                split_rectangles.append((fx, py + ph, fw, fy + fh - py - ph))
        free_rectangles = prune_free_rectangles(split_rectangles)
    return True


def pack(input_dir: Path, output_image: Path, output_json: Path, max_width: int, padding: int, alpha_threshold: int) -> dict:
    source_files = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and path.resolve() != output_image.resolve()
    )
    if not source_files:
        raise SystemExit(f"No images found under {input_dir}")

    items: list[dict] = []
    seen_ids: set[str] = set()
    for source_path in source_files:
        relative_path = source_path.relative_to(input_dir)
        asset_id = sprite_id(relative_path)
        if asset_id in seen_ids:
            raise SystemExit(f"Sprite ID collision: {asset_id}")
        seen_ids.add(asset_id)

        with Image.open(source_path) as opened:
            original = opened.convert("RGBA")
            trimmed, source_rect = trim_rgba(original, alpha_threshold)
            items.append(
                {
                    "id": asset_id,
                    "path": relative_path.as_posix(),
                    "image": trimmed,
                    "source_size": [original.width, original.height],
                    "source_rect": list(source_rect),
                }
            )

    atlas_width = max_width
    atlas_height = 256
    while not maxrects_pack(items, atlas_width, atlas_height, padding):
        atlas_height *= 2
        if atlas_height > 4096:
            raise SystemExit(f"Could not pack images into {atlas_width}x4096")

    used_height = max(item["packed_y"] + item["height"] + padding * 2 for item in items)
    atlas_height = next_power_of_two(used_height)

    atlas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
    sprites: dict[str, dict] = {}
    for item in items:
        padded = padded_with_extruded_edges(item["image"], padding)
        atlas.paste(padded, (item["packed_x"], item["packed_y"]), padded)
        source_rect = item["source_rect"]
        source_size = item["source_size"]
        sprites[item["id"]] = {
            "x": item["x"],
            "y": item["y"],
            "width": item["width"],
            "height": item["height"],
            "packed_x": item["packed_x"],
            "packed_y": item["packed_y"],
            "packed_width": item["width"] + padding * 2,
            "packed_height": item["height"] + padding * 2,
            "source_size": source_size,
            "source_rect": source_rect,
            "trimmed": source_rect != [0, 0, source_size[0], source_size[1]],
            "source_path": item["path"],
        }

    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(output_image, format="PNG", optimize=True)
    manifest = {
        "schema_version": "2.0",
        "atlas": {
            "image": output_image.name,
            "width": atlas.width,
            "height": atlas.height,
            "padding": padding,
            "extrude": True,
            "alpha_threshold": alpha_threshold,
            "trim": True,
            "square": atlas.width == atlas.height,
        },
        "sprites": sprites,
    }
    output_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-image", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--max-width", type=int, default=1024)
    parser.add_argument("--padding", type=int, default=3)
    parser.add_argument("--alpha-threshold", type=int, default=0)
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_image = (args.output_image or input_dir / "atlas.png").resolve()
    output_json = (args.output_json or input_dir / "atlas.json").resolve()
    manifest = pack(input_dir, output_image, output_json, args.max_width, args.padding, args.alpha_threshold)
    print(json.dumps({"image": str(output_image), "json": str(output_json), "size": [manifest["atlas"]["width"], manifest["atlas"]["height"]], "sprites": len(manifest["sprites"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
