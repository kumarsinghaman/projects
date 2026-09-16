"""Daily targets. Either set by hand or derived from body stats and a goal."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import nutrients

ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Calorie adjustment applied to maintenance for each weight goal.
GOAL_ADJUSTMENTS: dict[str, float] = {
    "lose": -0.18,
    "maintain": 0.0,
    "gain": 0.12,
}

# Protein grams per kg of body weight; higher while cutting to protect lean mass.
PROTEIN_PER_KG: dict[str, float] = {"lose": 1.8, "maintain": 1.6, "gain": 1.8}

DEFAULT_GOALS: dict[str, float] = {
    "kcal": 2200.0,
    "protein_g": 110.0,
    "carb_g": 260.0,
    "fiber_g": 30.0,
    "sugar_g": 55.0,
    "fat_g": 65.0,
    "sat_fat_g": 24.0,
    "sodium_mg": 2300.0,
    "potassium_mg": 3500.0,
}


@dataclass
class Profile:
    path: Path | None = None
    name: str = ""
    sex: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity: str | None = None
    weight_goal: str | None = None
    goals: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_GOALS))
    goals_source: str = "default"

    @classmethod
    def load(cls, path: Path) -> Profile:
        if not path.exists():
            return cls(path=path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        goals = raw.get("goals") or {}
        merged = dict(DEFAULT_GOALS)
        merged.update(
            {
                key: float(value)
                for key, value in goals.items()
                if key in nutrients.NUTRIENT_KEYS
            }
        )
        return cls(
            path=path,
            name=str(raw.get("name", "")),
            sex=(str(raw["sex"]) if raw.get("sex") else None),
            age=(int(raw["age"]) if raw.get("age") else None),
            height_cm=(float(raw["height_cm"]) if raw.get("height_cm") else None),
            weight_kg=(float(raw["weight_kg"]) if raw.get("weight_kg") else None),
            activity=(str(raw["activity"]) if raw.get("activity") else None),
            weight_goal=(str(raw["weight_goal"]) if raw.get("weight_goal") else None),
            goals=merged,
            goals_source=str(raw.get("goals_source", "default")),
        )

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save the profile to")
        payload: dict[str, object] = {"version": 1, "name": self.name}
        for key in ("sex", "age", "height_cm", "weight_kg", "activity", "weight_goal"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        payload["goals_source"] = self.goals_source
        payload["goals"] = {
            key: round(self.goals[key], 1)
            for key in nutrients.NUTRIENT_KEYS
            if key in self.goals
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    def goal_for(self, key: str) -> float | None:
        value = self.goals.get(key)
        return value if value and value > 0 else None

    def set_goals(self, updates: Mapping[str, float]) -> None:
        for key, value in updates.items():
            if key not in nutrients.NUTRIENT_KEYS:
                raise ValueError(f"unknown nutrient {key!r}")
            self.goals[key] = float(value)
        self.goals_source = "manual"

    def has_body_stats(self) -> bool:
        return None not in (self.sex, self.age, self.height_cm, self.weight_kg)

    def bmr(self) -> float:
        """Mifflin-St Jeor resting energy expenditure."""
        if not self.has_body_stats():
            raise ValueError(
                "sex, age, height_cm and weight_kg are all required to estimate BMR"
            )
        assert self.age is not None and self.height_cm is not None
        assert self.weight_kg is not None
        base = 10.0 * self.weight_kg + 6.25 * self.height_cm - 5.0 * self.age
        return base + (5.0 if (self.sex or "").lower().startswith("m") else -161.0)

    def maintenance_kcal(self) -> float:
        factor = ACTIVITY_FACTORS[(self.activity or "moderate").lower()]
        return self.bmr() * factor

    def recompute_goals(self) -> dict[str, float]:
        """Derive every daily target from body stats, activity and weight goal."""
        goal = (self.weight_goal or "maintain").lower()
        if goal not in GOAL_ADJUSTMENTS:
            raise ValueError(f"unknown weight goal {goal!r}")
        kcal = round(self.maintenance_kcal() * (1.0 + GOAL_ADJUSTMENTS[goal]))
        assert self.weight_kg is not None
        protein_g = round(self.weight_kg * PROTEIN_PER_KG[goal], 1)
        fat_g = round(kcal * 0.27 / 9.0, 1)
        carb_g = round(max(kcal - protein_g * 4.0 - fat_g * 9.0, 0.0) / 4.0, 1)
        self.goals = {
            "kcal": float(kcal),
            "protein_g": protein_g,
            "carb_g": carb_g,
            "fat_g": fat_g,
            "fiber_g": round(kcal / 1000.0 * 14.0, 1),
            "sugar_g": round(kcal * 0.10 / 4.0, 1),
            "sat_fat_g": round(kcal * 0.10 / 9.0, 1),
            "sodium_mg": 2300.0,
            "potassium_mg": 3500.0,
        }
        self.goals_source = "derived"
        return self.goals
