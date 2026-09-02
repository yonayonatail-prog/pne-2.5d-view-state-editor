"""Blender-independent state interpolation and residency logic."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ViewPoint:
    id: str
    yaw_deg: float
    pitch_deg: float = 0.0


@dataclass(frozen=True)
class ViewBlend:
    state_a: str
    state_b: str
    raw_t: float
    blend: float


@dataclass(frozen=True)
class Residency:
    active: tuple[str, ...]
    prefetch: tuple[str, ...]
    cache: tuple[str, ...]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def interpolate(value: float, mode: str) -> float:
    """Apply the editor's interpolation curve to a normalized value."""

    t = clamp01(value)
    mode = mode.upper()
    if mode == "SMOOTHSTEP":
        return t * t * (3.0 - 2.0 * t)
    if mode == "SHARP":
        if t in (0.0, 1.0):
            return t
        a = t * t
        b = (1.0 - t) * (1.0 - t)
        return a / (a + b)
    return t


def resolve_view_blend(yaw_deg: float, views: Iterable[ViewPoint], interpolation: str = "SMOOTHSTEP") -> ViewBlend:
    ordered = sorted(views, key=lambda item: (item.yaw_deg, item.id))
    if not ordered:
        return ViewBlend("", "", 0.0, 0.0)
    if len(ordered) == 1 or yaw_deg <= ordered[0].yaw_deg:
        return ViewBlend(ordered[0].id, ordered[0].id, 0.0, 0.0)
    if yaw_deg >= ordered[-1].yaw_deg:
        return ViewBlend(ordered[-1].id, ordered[-1].id, 0.0, 0.0)

    for left, right in zip(ordered, ordered[1:]):
        if left.yaw_deg <= yaw_deg <= right.yaw_deg:
            span = right.yaw_deg - left.yaw_deg
            raw = 0.0 if math.isclose(span, 0.0) else clamp01((yaw_deg - left.yaw_deg) / span)
            return ViewBlend(left.id, right.id, raw, interpolate(raw, interpolation))
    return ViewBlend(ordered[-1].id, ordered[-1].id, 0.0, 0.0)


def transition_weights(blend: float, transition: str) -> tuple[float, float]:
    """Return non-dither fallback weights for two adjacent states."""

    t = clamp01(blend)
    transition = transition.upper()
    if transition == "STEP":
        return (1.0, 0.0) if t < 0.5 else (0.0, 1.0)
    if transition == "SHARP":
        t = clamp01((t - 0.4) / 0.2)
    return 1.0 - t, t


def compute_residency(
    ordered_ids: Sequence[str],
    state_a: str,
    state_b: str,
    previous_cache: Sequence[str] = (),
    prefetch_views: int = 1,
    cache_views: int = 2,
) -> Residency:
    """Build active/prefetch/LRU sets without disposing boundary-neighbour views."""

    active = tuple(dict.fromkeys(view_id for view_id in (state_a, state_b) if view_id))
    indexes = [ordered_ids.index(view_id) for view_id in active if view_id in ordered_ids]
    candidates: list[str] = []
    if indexes:
        lo, hi = min(indexes), max(indexes)
        for distance in range(1, len(ordered_ids) + 1):
            for index in (hi + distance, lo - distance):
                if 0 <= index < len(ordered_ids):
                    item = ordered_ids[index]
                    if item not in active and item not in candidates:
                        candidates.append(item)
    prefetch = tuple(candidates[: max(0, prefetch_views)])

    cache_candidates: list[str] = []
    for item in (*active, *previous_cache, *ordered_ids):
        if item and item not in active and item not in prefetch and item not in cache_candidates:
            cache_candidates.append(item)
    cache = tuple(cache_candidates[: max(0, cache_views)])
    return Residency(active, prefetch, cache)
