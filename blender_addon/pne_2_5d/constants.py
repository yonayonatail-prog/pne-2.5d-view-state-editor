"""Shared schema constants."""

from __future__ import annotations

ADDON_VERSION = "0.1.1"
SCHEMA_VERSION = "0.1"
MASTER_COLLECTION = "PNE_2_5D_CHARACTER"
DEBUG_TEXT_NAME = "PNE_DEBUG_LOG"

VIEW_ROLE_ORDER = (
    "base",
    "jaw",
    "eye_l",
    "eye_r",
    "brow_l",
    "brow_r",
    "mouth",
    "occlusion",
)

REQUIRED_ROLES = frozenset(VIEW_ROLE_ORDER)

ROLE_RENDER_ORDER = {
    "base": 0,
    "jaw": 10,
    "eye_l": 20,
    "eye_r": 20,
    "brow_l": 21,
    "brow_r": 21,
    "mouth": 22,
    "occlusion": 30,
    "foreground": 40,
}

ROLE_CONCEPT_Z = {
    "base": 0.000,
    "jaw": 0.001,
    "eye_l": 0.002,
    "eye_r": 0.002,
    "brow_l": 0.002,
    "brow_r": 0.002,
    "mouth": 0.002,
    "occlusion": 0.003,
    "foreground": 0.004,
}

ROLE_TEXTURE_PACK = {
    "base": "base",
    "jaw": "jaw",
    "eye_l": "face_parts",
    "eye_r": "face_parts",
    "brow_l": "face_parts",
    "brow_r": "face_parts",
    "mouth": "face_parts",
    "occlusion": "occlusion",
    "foreground": "occlusion",
}

REQUIRED_SHAPE_KEYS = {
    "eye_l": ("Blink", "Wide", "Squint"),
    "eye_r": ("Blink", "Wide", "Squint"),
    "brow_l": ("Up", "Down", "InnerUp", "Angry"),
    "brow_r": ("Up", "Down", "InnerUp", "Angry"),
    "mouth": ("Open", "Wide", "Narrow", "Smile", "Frown"),
    "jaw": ("JawDown",),
}

TEXTURE_PACKS = ("base", "face_parts", "occlusion", "jaw")
