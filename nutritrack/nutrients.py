"""Nutrient vocabulary shared by the food database, the log and the reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple


class Nutrient(NamedTuple):
    key: str
    label: str
    unit: str
    decimals: int
    # True when the goal is a ceiling: sugar, saturated fat and sodium.
    is_limit: bool
    # True when going past the goal is harmless or desirable: protein, fiber,
    # potassium. Calories, carbs and fat are budgets, so overshooting matters.
    exceed_ok: bool = False


NUTRIENTS: tuple[Nutrient, ...] = (
    Nutrient("kcal", "Calories", "kcal", 0, False),
    Nutrient("protein_g", "Protein", "g", 1, False, exceed_ok=True),
    Nutrient("carb_g", "Carbs", "g", 1, False),
    Nutrient("fiber_g", "Fiber", "g", 1, False, exceed_ok=True),
    Nutrient("sugar_g", "Sugar", "g", 1, True),
    Nutrient("fat_g", "Fat", "g", 1, False),
    Nutrient("sat_fat_g", "Saturated fat", "g", 1, True),
    Nutrient("sodium_mg", "Sodium", "mg", 0, True),
    Nutrient("potassium_mg", "Potassium", "mg", 0, False, exceed_ok=True),
)

NUTRIENT_KEYS: tuple[str, ...] = tuple(n.key for n in NUTRIENTS)
BY_KEY: dict[str, Nutrient] = {n.key: n for n in NUTRIENTS}

# Macros carry these calories per gram; used to show where the day's energy came from.
KCAL_PER_GRAM = {"protein_g": 4.0, "carb_g": 4.0, "fat_g": 9.0}

MACRO_KEYS: tuple[str, ...] = ("protein_g", "carb_g", "fat_g")


def zeros() -> dict[str, float]:
    return dict.fromkeys(NUTRIENT_KEYS, 0.0)


def scale(per_100g: Mapping[str, float], grams: float) -> dict[str, float]:
    """Scale a per-100 g nutrient mapping to an arbitrary gram amount."""
    factor = grams / 100.0
    return {key: float(per_100g.get(key, 0.0)) * factor for key in NUTRIENT_KEYS}


def total(vectors: Iterable[Mapping[str, float]]) -> dict[str, float]:
    out = zeros()
    for vector in vectors:
        for key in NUTRIENT_KEYS:
            out[key] += float(vector.get(key, 0.0))
    return out


def macro_energy(vector: Mapping[str, float]) -> dict[str, float]:
    """Calories contributed by each macro."""
    return {key: float(vector.get(key, 0.0)) * KCAL_PER_GRAM[key] for key in MACRO_KEYS}


def macro_split(vector: Mapping[str, float]) -> dict[str, float]:
    """Percentage of macro calories from each macro. Empty intake yields zeros."""
    energy = macro_energy(vector)
    known = sum(energy.values())
    if known <= 0:
        return dict.fromkeys(MACRO_KEYS, 0.0)
    return {key: value / known * 100.0 for key, value in energy.items()}


def format_amount(key: str, value: float) -> str:
    nutrient = BY_KEY[key]
    return f"{value:.{nutrient.decimals}f}"


def format_with_unit(key: str, value: float) -> str:
    nutrient = BY_KEY[key]
    return f"{format_amount(key, value)} {nutrient.unit}"
