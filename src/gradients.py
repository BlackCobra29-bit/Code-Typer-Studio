from __future__ import annotations

from typing import Any


GRADIENT_PRESETS = [
    {
        "value": "sunset",
        "label": "Sunset",
        "angle": 135,
        "colors": ["#f6d365", "#fda085"],
    },
    {
        "value": "peach-fuzz",
        "label": "Peach Fuzz",
        "angle": 135,
        "colors": ["#f9d29d", "#f97393"],
    },
    {
        "value": "candy",
        "label": "Candy",
        "angle": 135,
        "colors": ["#fc5c7d", "#6a82fb"],
    },
    {
        "value": "ember",
        "label": "Ember",
        "angle": 135,
        "colors": ["#f12711", "#f5af19"],
    },
    {
        "value": "aurora",
        "label": "Aurora",
        "angle": 135,
        "colors": ["#7f7fd5", "#86a8e7", "#91eae4"],
    },
    {
        "value": "mint",
        "label": "Mint",
        "angle": 135,
        "colors": ["#11998e", "#38ef7d"],
    },
    {
        "value": "ocean",
        "label": "Ocean",
        "angle": 135,
        "colors": ["#43cea2", "#185a9d"],
    },
    {
        "value": "skyline",
        "label": "Skyline",
        "angle": 135,
        "colors": ["#56ccf2", "#2f80ed"],
    },
    {
        "value": "orchid",
        "label": "Orchid",
        "angle": 135,
        "colors": ["#c471f5", "#fa71cd"],
    },
    {
        "value": "midnight",
        "label": "Midnight",
        "angle": 135,
        "colors": ["#071321", "#080d16", "#07140f"],
    },
    {
        "value": "lagoon",
        "label": "Lagoon",
        "angle": 135,
        "colors": ["#4facfe", "#00f2fe"],
    },
    {
        "value": "rose-gold",
        "label": "Rose Gold",
        "angle": 135,
        "colors": ["#f7d9aa", "#f78ca0"],
    },
]

GRADIENT_BY_VALUE = {preset["value"]: preset for preset in GRADIENT_PRESETS}


def gradient_css(name: str) -> str:
    preset = GRADIENT_BY_VALUE.get(name, GRADIENT_PRESETS[0])
    stops = ", ".join(preset["colors"])
    return f"linear-gradient({preset['angle']}deg, {stops})"


def gradient_stops(name: str) -> list[str]:
    preset = GRADIENT_BY_VALUE.get(name, GRADIENT_PRESETS[0])
    return list(preset["colors"])


def gradient_catalog() -> list[dict[str, Any]]:
    return [dict(preset) for preset in GRADIENT_PRESETS]
